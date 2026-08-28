using System;
using System.Diagnostics;
using System.Drawing;
using System.IO;
using System.Net.Http;
using System.Text.RegularExpressions;
using System.Threading;
using System.Windows.Forms;

[STAThread]
static class Program
{
    static void Main()
    {
        Application.EnableVisualStyles();
        Application.SetCompatibleTextRenderingDefault(false);
        Application.Run(new TrayContext());
    }
}

class TrayContext : ApplicationContext
{
    private const string CurrentVersion   = "1.0.0";
    private const string ReleasesApi      = "https://api.github.com/repos/TJM-NZ/InterScribe/releases/latest";
    private const string ReleasesPage     = "https://github.com/TJM-NZ/InterScribe/releases/latest";

    private readonly NotifyIcon       _tray;
    private readonly ContextMenuStrip _menu;
    private readonly System.Threading.Timer _timer;
    private readonly string           _appDir;
    private bool _running = false;

    // Inserted just before the first separator when an update is found.
    private ToolStripMenuItem? _updateItem;

    public TrayContext()
    {
        _appDir = Path.GetDirectoryName(Application.ExecutablePath)!;

        var openItem  = new ToolStripMenuItem("Open InterScribe", null, OnOpen)
            { Font = new Font(SystemFonts.MenuFont!, FontStyle.Bold) };
        var startItem = new ToolStripMenuItem("Start services",   null, OnStart);
        var stopItem  = new ToolStripMenuItem("Stop services",    null, OnStop);
        var logsItem  = new ToolStripMenuItem("View logs",        null, OnLogs);
        var setupItem = new ToolStripMenuItem("Run setup",        null, OnSetup);
        var exitItem  = new ToolStripMenuItem("Exit",             null, OnExit);

        _menu = new ContextMenuStrip();
        _menu.Items.AddRange(new ToolStripItem[] {
            openItem, new ToolStripSeparator(),
            startItem, stopItem, new ToolStripSeparator(),
            logsItem, setupItem, new ToolStripSeparator(),
            exitItem,
        });

        _tray = new NotifyIcon
        {
            Icon             = MakeIcon(false),
            ContextMenuStrip = _menu,
            Text             = "InterScribe — stopped",
            Visible          = true,
        };
        _tray.DoubleClick += OnOpen;

        // Health check immediately, then every 30 s.
        _timer = new System.Threading.Timer(PollStatus, null, 0, 30_000);

        // Version check in background — no delay needed, non-blocking.
        new Thread(CheckForUpdate) { IsBackground = true }.Start();
    }

    // ── Icon ──────────────────────────────────────────────────────────────────

    private static Icon MakeIcon(bool running)
    {
        var bmp = new Bitmap(16, 16);
        using (var g = Graphics.FromImage(bmp))
        {
            g.Clear(Color.Transparent);
            var color = running
                ? Color.FromArgb(16, 185, 129)   // emerald
                : Color.FromArgb(156, 163, 175);  // gray
            using var brush = new SolidBrush(color);
            g.FillEllipse(brush, 1, 1, 14, 14);
        }
        return Icon.FromHandle(bmp.GetHicon());
    }

    // ── Health polling ────────────────────────────────────────────────────────

    private void PollStatus(object? _)
    {
        bool healthy = Probe();
        if (healthy == _running) return;
        _running = healthy;
        _tray.Icon = MakeIcon(healthy);
        _tray.Text = healthy ? "InterScribe — running" : "InterScribe — stopped";
    }

    private static bool Probe()
    {
        try
        {
            using var client = new HttpClient { Timeout = TimeSpan.FromSeconds(3) };
            var r = client.GetAsync("http://localhost:8002/health").Result;
            return r.IsSuccessStatusCode;
        }
        catch { return false; }
    }

    // ── Update check ──────────────────────────────────────────────────────────

    private void CheckForUpdate()
    {
        try
        {
            string json;
            using (var client = new HttpClient { Timeout = TimeSpan.FromSeconds(10) })
            {
                // GitHub API requires a User-Agent header.
                client.DefaultRequestHeaders.Add("User-Agent", "InterScribe-Tray");
                json = client.GetStringAsync(ReleasesApi).Result;
            }

            // Extract tag_name (e.g. "v1.2.0") without a JSON parser dependency.
            var tagMatch = Regex.Match(json, "\"tag_name\"\\s*:\\s*\"v?([^\"]+)\"");
            if (!tagMatch.Success) return;

            var latest  = new Version(tagMatch.Groups[1].Value);
            var current = new Version(CurrentVersion);
            if (latest <= current) return;

            // New version found — surface it on the UI thread.
            string label = $"Update available — v{latest}";
            _tray.ShowBalloonTip(
                8000, "InterScribe update available",
                $"Version {latest} is ready. Click here to download.",
                ToolTipIcon.Info);
            _tray.BalloonTipClicked += (_, __) => OpenReleasesPage();

            _menu.Invoke(new Action(() =>
            {
                _updateItem = new ToolStripMenuItem(label, null, (_, __) => OpenReleasesPage())
                {
                    ForeColor = Color.FromArgb(5, 150, 105), // emerald-600
                };
                // Insert at position 0, above "Open InterScribe".
                _menu.Items.Insert(0, _updateItem);
                _menu.Items.Insert(1, new ToolStripSeparator());
            }));
        }
        catch
        {
            // Silently ignore — no network, private repo not found, etc.
        }
    }

    private static void OpenReleasesPage()
        => Process.Start(new ProcessStartInfo(ReleasesPage) { UseShellExecute = true });

    // ── Docker Compose helpers ────────────────────────────────────────────────

    private void RunCompose(string args)
    {
        var psi = new ProcessStartInfo
        {
            FileName         = "docker",
            Arguments        = $"compose -f docker-compose.yml -f docker-compose.mac.yml {args}",
            WorkingDirectory = _appDir,
            UseShellExecute  = false,
            CreateNoWindow   = true,
        };
        using var p = Process.Start(psi);
        p?.WaitForExit();
    }

    // ── Menu handlers ─────────────────────────────────────────────────────────

    private void OnOpen(object? sender, EventArgs e)
        => Process.Start(new ProcessStartInfo("http://localhost:3002") { UseShellExecute = true });

    private void OnStart(object? sender, EventArgs e)
    {
        _tray.ShowBalloonTip(3000, "InterScribe", "Starting services…", ToolTipIcon.Info);
        new Thread(() =>
        {
            RunCompose("up -d");
            PollStatus(null);
            if (_running)
                _tray.ShowBalloonTip(3000, "InterScribe", "Services running — open http://localhost:3002", ToolTipIcon.Info);
        }) { IsBackground = true }.Start();
    }

    private void OnStop(object? sender, EventArgs e)
    {
        new Thread(() => RunCompose("down")) { IsBackground = true }.Start();
        _running = false;
        _tray.Icon = MakeIcon(false);
        _tray.Text = "InterScribe — stopped";
    }

    private void OnLogs(object? sender, EventArgs e)
    {
        Process.Start(new ProcessStartInfo
        {
            FileName         = "cmd",
            Arguments        = "/k docker compose -f docker-compose.yml -f docker-compose.mac.yml logs -f",
            WorkingDirectory = _appDir,
            UseShellExecute  = true,
        });
    }

    private void OnSetup(object? sender, EventArgs e)
    {
        var bat = Path.Combine(_appDir, "setup.bat");
        if (File.Exists(bat))
            Process.Start(new ProcessStartInfo(bat) { UseShellExecute = true });
    }

    private void OnExit(object? sender, EventArgs e)
    {
        _timer.Dispose();
        _tray.Visible = false;
        Application.Exit();
    }

    protected override void Dispose(bool disposing)
    {
        if (disposing)
        {
            _timer.Dispose();
            _tray.Dispose();
            _menu.Dispose();
        }
        base.Dispose(disposing);
    }
}

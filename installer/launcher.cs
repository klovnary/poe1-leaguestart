// League Start Tracker.exe: starts the tracker with the Python the installer put
// next to it (python\pythonw.exe app\main.py). No console window.
//   --console   show a console with any error messages (stays open after it exits)
using System;
using System.Diagnostics;
using System.IO;
using System.Linq;
using System.Reflection;
using System.Windows.Forms;

[assembly: AssemblyTitle("League Start Tracker")]
[assembly: AssemblyProduct("League Start Tracker")]
[assembly: AssemblyDescription("Path of Exile league start timer")]
[assembly: AssemblyCompany("klovnary")]

static class Launcher
{
    [STAThread]
    static int Main(string[] args)
    {
        string dir = AppDomain.CurrentDomain.BaseDirectory;
        bool console = args.Contains("--console");
        string py = Path.Combine(dir, "python", console ? "python.exe" : "pythonw.exe");
        string app = Path.Combine(dir, "app");
        string main = Path.Combine(app, "main.py");
        if (!File.Exists(py) || !File.Exists(main))
        {
            MessageBox.Show("Part of League Start Tracker is missing.\n\nRun the Setup again (your times are kept).",
                            "League Start Tracker", MessageBoxButtons.OK, MessageBoxIcon.Error);
            return 1;
        }
        ProcessStartInfo psi;
        if (console)
        {
            psi = new ProcessStartInfo("cmd.exe", "/k \"title League Start Tracker & \"" + py + "\" \"" + main + "\"\"");
            psi.UseShellExecute = true;
        }
        else
        {
            psi = new ProcessStartInfo(py, "\"" + main + "\"");
            psi.UseShellExecute = false;
        }
        psi.WorkingDirectory = app;
        try
        {
            Process.Start(psi);
        }
        catch (Exception e)
        {
            MessageBox.Show("Couldn't start League Start Tracker:\n\n" + e.Message, "League Start Tracker",
                            MessageBoxButtons.OK, MessageBoxIcon.Error);
            return 1;
        }
        return 0;
    }
}

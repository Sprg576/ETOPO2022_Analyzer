// GUI-subsystem host: CREATE_NO_WINDOW prevents a blank Windows Terminal tab.
using System;
using System.Diagnostics;
using System.IO;
using System.Reflection;
using System.Windows.Forms;

internal static class Launcher
{
    [STAThread]
    private static int Main(string[] args)
    {
        try
        {
            string root = Path.GetDirectoryName(Assembly.GetExecutingAssembly().Location);
            string mode = args.Length > 0 ? args[0] : "Run";
            if (mode != "Run" && mode != "Demo") throw new ArgumentException("Expected Run or Demo.");
            string command = "-NoProfile -ExecutionPolicy Bypass -File \"" + Path.Combine(root, "Launch.ps1") + "\" -Mode " + mode;
            if (args.Length == 3 && args[1] == "--verify-window")
                command += " -VerifyWindow -Report \"" + Path.GetFullPath(args[2]) + "\"";
            else if (args.Length > 1) throw new ArgumentException("Invalid launcher arguments.");
            string state = Environment.GetEnvironmentVariable("ETOPO_STATE_DIR");
            if (String.IsNullOrEmpty(state)) state = Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData), "ETOPO2022Analyzer");
            string logs = Path.Combine(state, "logs");
            Directory.CreateDirectory(logs);
            ProcessStartInfo info = new ProcessStartInfo();
            info.FileName = Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.Windows), "System32", "WindowsPowerShell", "v1.0", "powershell.exe");
            info.Arguments = command;
            info.WorkingDirectory = root;
            info.UseShellExecute = false;
            info.CreateNoWindow = true;
            info.RedirectStandardOutput = true;
            info.RedirectStandardError = true;
            using (Process process = Process.Start(info))
            {
                var output = process.StandardOutput.ReadToEndAsync();
                var errors = process.StandardError.ReadToEndAsync();
                process.WaitForExit();
                File.WriteAllText(Path.Combine(logs, "launcher-" + process.Id + ".log"), output.Result + errors.Result);
                return process.ExitCode;
            }
        }
        catch (Exception error)
        {
            MessageBox.Show(error.Message, "ETOPO2022 Analyzer - startup failed", MessageBoxButtons.OK, MessageBoxIcon.Error);
            return 1;
        }
    }
}

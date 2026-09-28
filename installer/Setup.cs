// Transcribe-Setup.exe: the same steps as install.bat, with the pins read from pins.txt beside the exe.
// Its logic stays fixed so its hash (and Windows reputation) carries over between releases; the pins change.
// Built by release.yml with the in-box .NET Framework 4.8 csc.exe, so the source is C# 5.
using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.IO;
using System.Reflection;
using System.Security.Cryptography;

static class Setup
{
    static readonly string[] PinKeys = { "UV_VERSION", "UV_SHA256", "UV_EXE_SHA256", "PYTHON_VERSION" };

    // Inherited settings that could redirect a download or its hashes are cleared.
    static readonly string[] Cleared = {
        "UV_PYTHON_DOWNLOADS_JSON_URL", "UV_PYTHON_INSTALL_MIRROR", "UV_CONFIG_FILE", "UV_PROJECT",
        "UV_WORKING_DIR", "UV_INDEX", "UV_INDEX_URL", "UV_DEFAULT_INDEX", "UV_EXTRA_INDEX_URL",
        "UV_FIND_LINKS", "UV_INSECURE_HOST", "SSL_CERT_FILE", "SSL_CERT_DIR",
    };

    class Fail : Exception
    {
        public Fail(string message) : base(message) { }
    }

    [STAThread]
    static int Main()
    {
        int code = 1;
        try
        {
            Install(AppDomain.CurrentDomain.BaseDirectory);
            code = 0;
            Console.WriteLine();
            Console.WriteLine("Done. Start the app with Transcribe.lnk in this folder.");
        }
        catch (Exception e)
        {
            Console.WriteLine((e.InnerException ?? e).Message);  // COM errors arrive wrapped
            Console.WriteLine();
            Console.WriteLine("Installation failed - see the message above. Running Transcribe-Setup.exe again resumes.");
        }
        if (Environment.GetEnvironmentVariable("CI") == null)
        {
            Console.WriteLine("Press Enter to close.");
            Console.ReadLine();
        }
        return code;
    }

    static void Install(string root)
    {
        string app = Path.Combine(root, "app");
        string pinsFile = Path.Combine(root, "pins.txt");
        if (!File.Exists(pinsFile) || !Directory.Exists(app))
            throw new Fail("Extract the whole zip first and run Transcribe-Setup.exe from the extracted folder.");
        Dictionary<string, string> pins = ReadPins(pinsFile);
        string sys = Path.Combine(Environment.GetEnvironmentVariable("SystemRoot"), "System32");
        string uvDir = Path.Combine(app, ".uv");
        string uvExe = Path.Combine(uvDir, "uv.exe");
        string tmp = Path.Combine(uvDir, "tmp");

        // Inherited by uv and Python: everything lands in this folder (see install.bat).
        Environment.SetEnvironmentVariable("UV_CACHE_DIR", Path.Combine(uvDir, "cache"));
        Environment.SetEnvironmentVariable("UV_PYTHON_INSTALL_DIR", Path.Combine(uvDir, "python"));
        Environment.SetEnvironmentVariable("UV_PROJECT_ENVIRONMENT", Path.Combine(app, ".venv"));
        Environment.SetEnvironmentVariable("UV_NO_CONFIG", "1");
        Environment.SetEnvironmentVariable("UV_PYTHON_PREFERENCE", "only-managed");
        Environment.SetEnvironmentVariable("UV_SYSTEM_CERTS", "1");
        foreach (string name in Cleared) Environment.SetEnvironmentVariable(name, null);
        Directory.CreateDirectory(tmp);
        Environment.SetEnvironmentVariable("TMP", tmp);
        Environment.SetEnvironmentVariable("TEMP", tmp);
        Environment.SetEnvironmentVariable("UV_PYTHON_INSTALL_BIN", "0");
        Environment.SetEnvironmentVariable("UV_PYTHON_INSTALL_REGISTRY", "0");

        // uv.exe is re-hashed on every run; a changed one is downloaded again.
        if (File.Exists(uvExe) && !HashIs(uvExe, pins["UV_EXE_SHA256"])) File.Delete(uvExe);
        if (!File.Exists(uvExe))
        {
            Console.WriteLine("Downloading uv " + pins["UV_VERSION"] + " ...");
            string zip = Path.Combine(uvDir, "uv.zip");
            string url = "https://github.com/astral-sh/uv/releases/download/" + pins["UV_VERSION"]
                + "/uv-x86_64-pc-windows-msvc.zip";
            // Relative to app\ as in install.bat, so curl and tar never see a non-ASCII folder name.
            Run(Path.Combine(sys, "curl.exe"), @"-fL -o .uv\uv.zip " + Quote(url), app);
            if (!HashIs(zip, pins["UV_SHA256"]))
            {
                File.Delete(zip);
                throw new Fail("The uv download does not match the pinned SHA-256.\nExpected: " + pins["UV_SHA256"]);
            }
            Run(Path.Combine(sys, "tar.exe"), @"-xf .uv\uv.zip -C .uv", app);
            File.Delete(zip);
        }
        if (!HashIs(uvExe, pins["UV_EXE_SHA256"])) throw new Fail("uv.exe does not match the pinned SHA-256.");

        Console.WriteLine("Installing Python " + pins["PYTHON_VERSION"] + " and the locked dependencies ...");
        Run(uvExe, "sync --frozen --no-dev --python " + pins["PYTHON_VERSION"], app);

        Console.WriteLine("Downloading and verifying the models (about 3 GB) ...");
        Run(Path.Combine(app, @".venv\Scripts\python.exe"), "-m transcribe_offline.setup", app);

        // Made here, so it carries no Mark of the Web; its working directory makes the package importable.
        Console.WriteLine("Creating Transcribe.lnk ...");
        CreateShortcut(Path.Combine(root, "Transcribe.lnk"), Path.Combine(app, @".venv\Scripts\pythonw.exe"), app);
    }

    // Only the four pin keys are taken; any other line is ignored (as in install.bat).
    static Dictionary<string, string> ReadPins(string path)
    {
        var pins = new Dictionary<string, string>();
        foreach (string raw in File.ReadAllLines(path))
        {
            string line = raw.Trim();
            int eq = line.IndexOf('=');
            if (line.StartsWith("#") || eq < 1) continue;
            string key = line.Substring(0, eq);
            if (Array.IndexOf(PinKeys, key) >= 0) pins[key] = line.Substring(eq + 1);
        }
        foreach (string key in PinKeys)
            if (!pins.ContainsKey(key)) throw new Fail("pins.txt beside Transcribe-Setup.exe has no " + key + ".");
        return pins;
    }

    static bool HashIs(string path, string expected)
    {
        using (FileStream stream = File.OpenRead(path))
        using (SHA256 sha = SHA256.Create())
        {
            string actual = BitConverter.ToString(sha.ComputeHash(stream)).Replace("-", "");
            return actual.Equals(expected, StringComparison.OrdinalIgnoreCase);
        }
    }

    static string Quote(string arg)
    {
        return "\"" + arg + "\"";
    }

    static void Run(string exe, string args, string workingDirectory)
    {
        var start = new ProcessStartInfo(exe, args) { UseShellExecute = false, WorkingDirectory = workingDirectory };
        using (Process process = Process.Start(start))
        {
            process.WaitForExit();
            if (process.ExitCode != 0)
                throw new Fail(Path.GetFileName(exe) + " failed with exit code " + process.ExitCode + ".");
        }
    }

    static void CreateShortcut(string lnk, string target, string workingDirectory)
    {
        Type shellType = Type.GetTypeFromProgID("WScript.Shell");
        object shell = Activator.CreateInstance(shellType);
        object link = shellType.InvokeMember("CreateShortcut", BindingFlags.InvokeMethod, null, shell, new object[] { lnk });
        Type linkType = link.GetType();
        linkType.InvokeMember("TargetPath", BindingFlags.SetProperty, null, link, new object[] { target });
        linkType.InvokeMember("Arguments", BindingFlags.SetProperty, null, link, new object[] { "-m transcribe_offline" });
        linkType.InvokeMember("WorkingDirectory", BindingFlags.SetProperty, null, link, new object[] { workingDirectory });
        linkType.InvokeMember("Save", BindingFlags.InvokeMethod, null, link, null);
    }
}

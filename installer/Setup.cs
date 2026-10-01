// Transcribe-Setup.exe: the same steps as install.bat, with the pins read from pins.txt beside the exe.
// Its logic stays fixed so its hash (and Windows reputation) carries over between releases; the pins change.
// Built by release.yml with the in-box .NET Framework 4.8 csc.exe, so the source is C# 5.
// It downloads and unzips in managed code and starts only uv and Python: a small unsigned exe that spawns
// curl.exe and tar.exe, or drives WScript.Shell, matches antivirus heuristics for a downloader.
using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.IO;
using System.IO.Compression;
using System.Net;
using System.Reflection;
using System.Runtime.InteropServices;
using System.Security.Cryptography;
using System.Text;

// Identifies the exe in Properties > Details (csc turns these into its version resource).
// The version is the installer's own, not the app's: it changes only with this file (see release.yml).
[assembly: AssemblyTitle("Transcribe Offline setup")]
[assembly: AssemblyDescription("Installs Transcribe Offline into the folder it is run from, verifying every download against the hashes in pins.txt.")]
[assembly: AssemblyProduct("Transcribe Offline")]
[assembly: AssemblyCompany("https://github.com/KristjanHS/transcribe-offline")]
[assembly: AssemblyCopyright("MIT License")]
[assembly: AssemblyVersion("1.1.0.0")]
[assembly: AssemblyFileVersion("1.1.0.0")]

static class Setup
{
    static readonly string[] PinKeys = { "UV_VERSION", "UV_SHA256", "UV_EXE_SHA256", "PYTHON_VERSION" };

    // Inherited settings that could redirect a download or its hashes are cleared.
    static readonly string[] Cleared = {
        "UV_PYTHON_DOWNLOADS_JSON_URL", "UV_PYTHON_INSTALL_MIRROR", "UV_CONFIG_FILE", "UV_PROJECT",
        "UV_WORKING_DIR", "UV_INDEX", "UV_INDEX_URL", "UV_DEFAULT_INDEX", "UV_EXTRA_INDEX_URL",
        "UV_FIND_LINKS", "UV_INSECURE_HOST", "SSL_CERT_FILE", "SSL_CERT_DIR",
    };

    // Written by install.bat too; its %~dp0 makes it relocatable, its working directory makes the package importable.
    const string Launcher = "@cd /d \"%~dp0app\"\r\n@start \"\" \".venv\\Scripts\\pythonw.exe\" -m transcribe_offline\r\n";

    class Fail : Exception
    {
        public Fail(string message) : base(message) { }
    }

    static int Main()
    {
        int code = 1;
        try
        {
            string root = InstallRoot();
            Install(root);
            code = 0;
            Console.WriteLine();
            Console.WriteLine("Done. Start the app with Transcribe.bat in " + root);
        }
        catch (Exception e)
        {
            Console.WriteLine((e.InnerException ?? e).Message);  // download errors arrive wrapped
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

    // The folder of the exe itself, also when started through a symlink (winget's Links folder).
    static string InstallRoot()
    {
        using (FileStream stream = File.OpenRead(Process.GetCurrentProcess().MainModule.FileName))
        {
            var path = new StringBuilder(32768);
            int length = GetFinalPathNameByHandle(stream.SafeFileHandle.DangerousGetHandle(), path, path.Capacity, 0);
            if (length <= 0 || length > path.Capacity) throw new Fail("Cannot resolve the path of Transcribe-Setup.exe.");
            string exe = path.ToString();
            if (exe.StartsWith(@"\\?\UNC\")) exe = @"\\" + exe.Substring(8);
            else if (exe.StartsWith(@"\\?\")) exe = exe.Substring(4);
            return Path.GetDirectoryName(exe);
        }
    }

    [DllImport("kernel32.dll", CharSet = CharSet.Unicode, SetLastError = true)]
    static extern int GetFinalPathNameByHandle(IntPtr file, StringBuilder path, int capacity, int flags);

    static void Install(string root)
    {
        string app = Path.Combine(root, "app");
        string pinsFile = Path.Combine(root, "pins.txt");
        if (!File.Exists(pinsFile) || !Directory.Exists(app))
            throw new Fail("Extract the whole zip first and run Transcribe-Setup.exe from the extracted folder.");
        Dictionary<string, string> pins = ReadPins(pinsFile);
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
            Download("https://github.com/astral-sh/uv/releases/download/" + pins["UV_VERSION"]
                + "/uv-x86_64-pc-windows-msvc.zip", zip);
            if (!HashIs(zip, pins["UV_SHA256"]))
            {
                File.Delete(zip);
                throw new Fail("The uv download does not match the pinned SHA-256.\nExpected: " + pins["UV_SHA256"]);
            }
            Unzip(zip, uvDir);
            File.Delete(zip);
        }
        if (!HashIs(uvExe, pins["UV_EXE_SHA256"])) throw new Fail("uv.exe does not match the pinned SHA-256.");

        Console.WriteLine("Installing Python " + pins["PYTHON_VERSION"] + " and the locked dependencies ...");
        Run(uvExe, "sync --frozen --no-dev --python " + pins["PYTHON_VERSION"], app);

        Console.WriteLine("Downloading and verifying the models (about 3 GB) ...");
        Run(Path.Combine(app, @".venv\Scripts\python.exe"), "-m transcribe_offline.setup", app);

        // Made here, so it carries no Mark of the Web.
        Console.WriteLine("Creating Transcribe.bat ...");
        File.WriteAllText(Path.Combine(root, "Transcribe.bat"), Launcher);
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

    // Windows' own TLS stack and certificate store (as curl.exe in install.bat); redirects are followed.
    static void Download(string url, string path)
    {
        ServicePointManager.SecurityProtocol = SecurityProtocolType.Tls12;
        using (var client = new WebClient())
        {
            client.Headers[HttpRequestHeader.UserAgent] = "Transcribe-Setup";
            client.DownloadFile(url, path);
        }
    }

    // Each entry is written under its bare file name, so no entry path can escape the folder.
    static void Unzip(string zip, string dir)
    {
        using (ZipArchive archive = ZipFile.OpenRead(zip))
            foreach (ZipArchiveEntry entry in archive.Entries)
            {
                string name = Path.GetFileName(entry.FullName);
                if (name.Length > 0) entry.ExtractToFile(Path.Combine(dir, name), true);
            }
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
}

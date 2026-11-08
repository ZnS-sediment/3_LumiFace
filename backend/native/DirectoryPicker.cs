// Windows Common Item Dialog; no PowerShell startup or invisible owner window.
// https://learn.microsoft.com/windows/win32/api/shobjidl_core/nn-shobjidl_core-ifiledialog
using System;
using System.Diagnostics;
using System.IO;
using System.Runtime.InteropServices;
using System.Text;
using System.Threading;

internal static class DirectoryPicker
{
    private const int Cancelled = unchecked((int)0x800704C7);
    private static readonly IntPtr TopMost = new IntPtr(-1);
    private static volatile bool finished;
    private static long shownMilliseconds = -1;
    private static bool foreground;
    private static bool topmost;
    private static uint windowDpi;
    private static bool perMonitorV2;
    private delegate bool EnumWindow(IntPtr window, IntPtr state);

    [DllImport("user32.dll")] private static extern IntPtr GetForegroundWindow();
    [DllImport("user32.dll")] private static extern bool SetForegroundWindow(IntPtr window);
    [DllImport("user32.dll")] private static extern bool IsWindowVisible(IntPtr window);
    [DllImport("user32.dll")] private static extern bool EnumThreadWindows(uint thread, EnumWindow callback, IntPtr state);
    [DllImport("user32.dll", CharSet = CharSet.Unicode)] private static extern int GetClassName(IntPtr window, StringBuilder name, int size);
    [DllImport("user32.dll")] private static extern bool SetWindowPos(IntPtr window, IntPtr after, int x, int y, int width, int height, uint flags);
    [DllImport("user32.dll")] private static extern int GetWindowLong(IntPtr window, int index);
    [DllImport("user32.dll")] private static extern bool PostMessage(IntPtr window, uint message, IntPtr wParam, IntPtr lParam);
    [DllImport("kernel32.dll")] private static extern uint GetCurrentThreadId();
    [DllImport("user32.dll")] private static extern uint GetDpiForWindow(IntPtr window);
    [DllImport("user32.dll")] private static extern IntPtr GetWindowDpiAwarenessContext(IntPtr window);
    [DllImport("user32.dll")] private static extern bool AreDpiAwarenessContextsEqual(IntPtr first, IntPtr second);

    private static void Present(uint thread, Stopwatch clock, bool diagnose)
    {
        // Act once, only on this process's dialog, instead of repeatedly stealing focus.
        while (!finished && clock.ElapsedMilliseconds < 15000)
        {
            IntPtr found = IntPtr.Zero;
            EnumThreadWindows(thread, delegate(IntPtr window, IntPtr state)
            {
                var name = new StringBuilder(64);
                GetClassName(window, name, name.Capacity);
                if (name.ToString() == "#32770" && IsWindowVisible(window))
                {
                    found = window;
                    return false;
                }
                return true;
            }, IntPtr.Zero);
            if (found != IntPtr.Zero)
            {
                if (diagnose)
                {
                    try
                    {
                        windowDpi = GetDpiForWindow(found);
                        perMonitorV2 = AreDpiAwarenessContextsEqual(
                            GetWindowDpiAwarenessContext(found), new IntPtr(-4));
                    }
                    catch (EntryPointNotFoundException) { } // Legacy Windows uses manifest fallback.
                }
                // TOPMOST affects the actual picker, not a transparent placeholder.
                SetWindowPos(found, TopMost, 0, 0, 0, 0, 0x0001 | 0x0002 | 0x0040 | 0x0200);
                SetForegroundWindow(found);
                shownMilliseconds = clock.ElapsedMilliseconds;
                foreground = GetForegroundWindow() == found;
                topmost = (GetWindowLong(found, -20) & 0x00000008) != 0;
                if (diagnose)
                {
                    Thread.Sleep(600);
                    PostMessage(found, 0x0010, IntPtr.Zero, IntPtr.Zero);
                }
                return;
            }
            Thread.Sleep(15);
        }
    }

    [STAThread]
    private static int Main(string[] args)
    {
        if (args.Length < 1) return 1;
        string output = args[0];
        if (args.Length == 2 && args[1] == "--probe")
        {
            File.WriteAllText(output, "ready", new UTF8Encoding(false));
            return 0;
        }
        bool diagnose = args.Length == 2 && args[1] == "--diagnose";
        if (diagnose)
        {
            var guard = new Thread(delegate() {
                Thread.Sleep(10000);
                if (!finished) Process.GetCurrentProcess().Kill();
            });
            guard.IsBackground = true;
            guard.Start();
        }
        var clock = Stopwatch.StartNew();
        IFileDialog dialog = null;
        IShellItem selected = null;
        Thread presenter = null;
        try
        {
            var type = Type.GetTypeFromCLSID(new Guid("DC1C5A9C-E88A-4DDE-A5A1-60F82A20AEF7"));
            dialog = (IFileDialog)Activator.CreateInstance(type);
            uint options;
            dialog.GetOptions(out options);
            dialog.SetOptions(options | 0x20 | 0x40 | 0x08 | 0x800 | 0x02000000);
            dialog.SetTitle("LumiFace - 选择照片根目录");
            dialog.SetOkButtonLabel("选择此文件夹");
            var client = new Guid("DA8A7994-6126-43AF-83C5-3DDDD4563757");
            dialog.SetClientGuid(ref client);
            uint thread = GetCurrentThreadId();
            presenter = new Thread(delegate() { Present(thread, clock, diagnose); });
            presenter.IsBackground = true;
            presenter.Start();
            // The browser is another process: do not disable it as a foreign modal owner.
            int result = dialog.Show(IntPtr.Zero);
            if (result != Cancelled) Marshal.ThrowExceptionForHR(result);
            if (diagnose)
            {
                File.WriteAllText(output, "{\"shown_ms\":" + shownMilliseconds + ",\"foreground\":" +
                    foreground.ToString().ToLowerInvariant() + ",\"topmost\":" + topmost.ToString().ToLowerInvariant() + ",\"dpi\":" + windowDpi +
                    ",\"per_monitor_v2\":" + perMonitorV2.ToString().ToLowerInvariant() + "}", new UTF8Encoding(false));
                return shownMilliseconds >= 0 && topmost ? 0 : 2;
            }
            if (result == Cancelled) { File.WriteAllText(output, ""); return 0; }
            dialog.GetResult(out selected);
            IntPtr text;
            selected.GetDisplayName(0x80058000, out text); // SIGDN_FILESYSPATH
            try
            {
                string path = Marshal.PtrToStringUni(text);
                File.WriteAllText(output, Convert.ToBase64String(Encoding.UTF8.GetBytes(path)), new UTF8Encoding(false));
            }
            finally { Marshal.FreeCoTaskMem(text); }
            return 0;
        }
        catch (Exception error)
        {
            File.WriteAllText(output, "error:" + error.Message, new UTF8Encoding(false));
            return 1;
        }
        finally
        {
            finished = true;
            if (presenter != null) presenter.Join(1000);
            if (selected != null) Marshal.ReleaseComObject(selected);
            if (dialog != null) Marshal.ReleaseComObject(dialog);
        }
    }

    [ComImport, Guid("42F85136-DB7E-439C-85F1-E4075D135FC8"), InterfaceType(ComInterfaceType.InterfaceIsIUnknown)]
    private interface IFileDialog
    {
        [PreserveSig] int Show(IntPtr owner);
        void SetFileTypes(uint count, IntPtr filters);
        void SetFileTypeIndex(uint index);
        void GetFileTypeIndex(out uint index);
        void Advise(IntPtr events, out uint cookie);
        void Unadvise(uint cookie);
        void SetOptions(uint options);
        void GetOptions(out uint options);
        void SetDefaultFolder(IShellItem folder);
        void SetFolder(IShellItem folder);
        void GetFolder(out IShellItem folder);
        void GetCurrentSelection(out IShellItem item);
        void SetFileName([MarshalAs(UnmanagedType.LPWStr)] string name);
        void GetFileName(out IntPtr name);
        void SetTitle([MarshalAs(UnmanagedType.LPWStr)] string title);
        void SetOkButtonLabel([MarshalAs(UnmanagedType.LPWStr)] string label);
        void SetFileNameLabel([MarshalAs(UnmanagedType.LPWStr)] string label);
        void GetResult(out IShellItem item);
        void AddPlace(IShellItem folder, uint placement);
        void SetDefaultExtension([MarshalAs(UnmanagedType.LPWStr)] string extension);
        void Close(int result);
        void SetClientGuid(ref Guid client);
        void ClearClientData();
        void SetFilter(IntPtr filter);
    }

    [ComImport, Guid("43826D1E-E718-42EE-BC55-A1E261C37BFE"), InterfaceType(ComInterfaceType.InterfaceIsIUnknown)]
    private interface IShellItem
    {
        void BindToHandler(IntPtr context, ref Guid handler, ref Guid id, out IntPtr result);
        void GetParent(out IShellItem parent);
        void GetDisplayName(uint kind, out IntPtr name);
        void GetAttributes(uint mask, out uint attributes);
        void Compare(IShellItem other, uint hint, out int order);
    }
}

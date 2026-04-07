using System;
using System.Collections.Generic;
using System.Runtime.InteropServices;
using System.Text;
using System.Text.Json;

const int WM_INPUT = 0x00FF;
const uint RID_INPUT = 0x10000003;
const uint RIDEV_INPUTSINK = 0x00000100;
const uint RIDEV_DEVNOTIFY = 0x00002000;
const uint RIM_TYPEHID = 2;
const uint RIDI_DEVICENAME = 0x20000007;
Console.OutputEncoding = Encoding.UTF8;
var helperClass = "WheelButtonListener";
NativeMethods.WndProc? wndProc = null;
var hInstance = NativeMethods.GetModuleHandleW(IntPtr.Zero);
var hwndMessage = new IntPtr(-3);
wndProc = new NativeMethods.WndProc(ProcessMessage);

var wndClass = new NativeMethods.WNDCLASSEX
{
    cbSize = (uint)Marshal.SizeOf<NativeMethods.WNDCLASSEX>(),
    lpfnWndProc = Marshal.GetFunctionPointerForDelegate(wndProc!),
    hInstance = hInstance,
    lpszClassName = helperClass,
};

if (NativeMethods.RegisterClassExW(ref wndClass) == 0)
{
    WriteLineAndExit("RegisterClassExW failed");
}

var hwnd = NativeMethods.CreateWindowExW(
    0,
    helperClass,
    helperClass,
    0,
    0,
    0,
    0,
    0,
    hwndMessage,
    IntPtr.Zero,
    hInstance,
    IntPtr.Zero);

if (hwnd == IntPtr.Zero)
{
    WriteLineAndExit("CreateWindowExW failed");
}

var devices = new[]
{
    new NativeMethods.RAWINPUTDEVICE
    {
        usUsagePage = 0x01,
        usUsage = 0x04,
        dwFlags = RIDEV_INPUTSINK | RIDEV_DEVNOTIFY,
        hwndTarget = hwnd,
    },
    new NativeMethods.RAWINPUTDEVICE
    {
        usUsagePage = 0x01,
        usUsage = 0x05,
        dwFlags = RIDEV_INPUTSINK | RIDEV_DEVNOTIFY,
        hwndTarget = hwnd,
    },
    new NativeMethods.RAWINPUTDEVICE
    {
        usUsagePage = 0x01,
        usUsage = 0x02,
        dwFlags = RIDEV_INPUTSINK | RIDEV_DEVNOTIFY,
        hwndTarget = hwnd,
    },
};

if (!NativeMethods.RegisterRawInputDevices(devices, (uint)devices.Length, (uint)Marshal.SizeOf<NativeMethods.RAWINPUTDEVICE>()))
{
    WriteLineAndExit($"RegisterRawInputDevices failed ({Marshal.GetLastWin32Error()})");
}

Console.CancelKeyPress += (_, _) =>
{
    NativeMethods.PostQuitMessage(0);
};

var msg = new NativeMethods.MSG();
while (NativeMethods.GetMessageW(out msg, IntPtr.Zero, 0, 0) > 0)
{
    NativeMethods.TranslateMessage(ref msg);
    NativeMethods.DispatchMessageW(ref msg);
}

return;

IntPtr ProcessMessage(IntPtr hwnd, uint msg, IntPtr wParam, IntPtr lParam)
{
    if (msg == WM_INPUT)
    {
        ProcessRawInput(lParam);
        return IntPtr.Zero;
    }

    return NativeMethods.DefWindowProcW(hwnd, msg, wParam, lParam);
}

void ProcessRawInput(IntPtr lParam)
{
    var headerSize = (uint)Marshal.SizeOf<NativeMethods.RAWINPUTHEADER>();
    var size = 0u;
    if (NativeMethods.GetRawInputData(lParam, RID_INPUT, IntPtr.Zero, ref size, headerSize) == unchecked((uint)-1) ||
        size == 0)
    {
        return;
    }

    var buffer = Marshal.AllocHGlobal((int)size);
    try
    {
        if (NativeMethods.GetRawInputData(lParam, RID_INPUT, buffer, ref size, headerSize) == unchecked((uint)-1))
        {
            return;
        }

        var header = Marshal.PtrToStructure<NativeMethods.RAWINPUTHEADER>(buffer);
        if (header.dwType != RIM_TYPEHID)
        {
            return;
        }

        ProcessHidInput(header, buffer, size);
    }
    finally
    {
        Marshal.FreeHGlobal(buffer);
    }
}

void ProcessHidInput(NativeMethods.RAWINPUTHEADER header, IntPtr buffer, uint size)
{
    var hidHeaderPtr = IntPtr.Add(buffer, Marshal.SizeOf<NativeMethods.RAWINPUTHEADER>());
    var rawHid = Marshal.PtrToStructure<NativeMethods.RAWHID>(hidHeaderPtr);
    if (rawHid.dwCount == 0 || rawHid.dwSizeHid == 0)
    {
        return;
    }

    int totalBytes = checked((int)(rawHid.dwCount * rawHid.dwSizeHid));
    var dataOffset = Marshal.SizeOf<NativeMethods.RAWHID>();
    var dataPtr = IntPtr.Add(hidHeaderPtr, dataOffset);
    var info = GetOrCreateHidDeviceInfo(header.hDevice, rawHid);
    if (info == null)
    {
        return;
    }

    if (info.InputReportBuffer.Length < totalBytes)
    {
        info.InputReportBuffer = new byte[totalBytes];
    }

    Marshal.Copy(dataPtr, info.InputReportBuffer, 0, totalBytes);
    ProcessHidReport(info, info.InputReportBuffer, totalBytes);
}

void ProcessHidReport(HidDeviceInfo info, byte[] report, int reportLength)
{
    if (info.LastReport == null || info.LastReport.Length != reportLength)
    {
        info.LastReport = new byte[reportLength];
    }

    for (var i = 0; i < reportLength; i++)
    {
        var prev = info.LastReport[i];
        var current = report[i];
        var diff = (byte)(prev ^ current);
        if (diff == 0)
        {
            continue;
        }

        for (var bit = 0; bit < 8; bit++)
        {
            if ((diff & (1 << bit)) == 0)
            {
                continue;
            }
            var buttonId = i * 8 + bit + 1;
            var pressedNow = ((current >> bit) & 1) != 0;
            EmitEvent(buttonId, pressedNow);
        }
        info.LastReport[i] = current;
    }
}

HidDeviceInfo GetOrCreateHidDeviceInfo(IntPtr hDevice, NativeMethods.RAWHID rawHid)
{
    if (DeviceTracker.TrackedDevices.TryGetValue(hDevice, out var info))
    {
        return info;
    }

    var name = GetRawInputDeviceName(hDevice);
    Console.Error.WriteLine($"Tracking RAWINPUT device: {name} bytes={rawHid.dwSizeHid}");
    info = new HidDeviceInfo(rawHid.dwSizeHid);
    DeviceTracker.TrackedDevices[hDevice] = info;
    return info;
}

string GetRawInputDeviceName(IntPtr hDevice)
{
    var size = 0u;
    NativeMethods.GetRawInputDeviceInfoW(hDevice, RIDI_DEVICENAME, IntPtr.Zero, ref size);
    if (size == 0)
    {
        return string.Empty;
    }

    var nameBuffer = new StringBuilder((int)size);
    NativeMethods.GetRawInputDeviceInfoW(hDevice, RIDI_DEVICENAME, nameBuffer, ref size);
    return nameBuffer.ToString();
}

void EmitEvent(int button, bool pressed)
{
    var payload = JsonSerializer.Serialize(new { button, pressed });
    Console.Out.WriteLine(payload);
    Console.Out.Flush();
}

void WriteLineAndExit(string message)
{
    Console.Error.WriteLine(message);
    Environment.Exit(1);
}

internal static class DeviceTracker
{
    public static readonly Dictionary<IntPtr, HidDeviceInfo> TrackedDevices = new();
}

internal sealed class HidDeviceInfo
{
    public byte[] InputReportBuffer { get; set; }
    public byte[] LastReport { get; set; }

    public HidDeviceInfo(uint reportLength)
    {
        InputReportBuffer = new byte[reportLength];
        LastReport = new byte[reportLength];
    }
}

internal static class NativeMethods
{
    public delegate IntPtr WndProc(IntPtr hwnd, uint msg, IntPtr wParam, IntPtr lParam);
    [DllImport("user32.dll", SetLastError = true, CharSet = CharSet.Unicode)]
    public static extern ushort RegisterClassExW([In] ref WNDCLASSEX lpwcx);

    [DllImport("user32.dll", SetLastError = true, CharSet = CharSet.Unicode)]
    public static extern IntPtr CreateWindowExW(
        uint dwExStyle,
        string lpClassName,
        string lpWindowName,
        uint dwStyle,
        int x,
        int y,
        int nWidth,
        int nHeight,
        IntPtr hWndParent,
        IntPtr hMenu,
        IntPtr hInstance,
        IntPtr lpParam);

    [DllImport("user32.dll")]
    public static extern IntPtr DefWindowProcW(IntPtr hWnd, uint Msg, IntPtr wParam, IntPtr lParam);

    [DllImport("user32.dll", SetLastError = true)]
    public static extern bool RegisterRawInputDevices(
        [In] RAWINPUTDEVICE[] pRawInputDevices,
        uint uiNumDevices,
        uint cbSize);

    [DllImport("user32.dll", SetLastError = true)]
    public static extern uint GetRawInputData(
        IntPtr hRawInput,
        uint uiCommand,
        IntPtr pData,
        ref uint pcbSize,
        uint cbSizeHeader);

    [DllImport("user32.dll", SetLastError = true)]
    public static extern int GetMessageW(out MSG lpMsg, IntPtr hWnd, uint wMsgFilterMin, uint wMsgFilterMax);

    [DllImport("user32.dll")]
    public static extern bool TranslateMessage([In] ref MSG lpMsg);

    [DllImport("user32.dll")]
    public static extern IntPtr DispatchMessageW([In] ref MSG lpMsg);

    [DllImport("user32.dll")]
    public static extern void PostQuitMessage(int nExitCode);

    [DllImport("kernel32.dll", CharSet = CharSet.Unicode, SetLastError = true)]
    public static extern IntPtr GetModuleHandleW(IntPtr lpModuleName);

    [DllImport("user32.dll", SetLastError = true, CharSet = CharSet.Unicode)]
    public static extern uint GetRawInputDeviceInfoW(
        IntPtr hDevice,
        uint uiCommand,
        StringBuilder pData,
        ref uint pcbSize);

    [DllImport("user32.dll", SetLastError = true)]
    public static extern uint GetRawInputDeviceInfoW(
        IntPtr hDevice,
        uint uiCommand,
        IntPtr pData,
        ref uint pcbSize);

    [StructLayout(LayoutKind.Sequential, CharSet = CharSet.Unicode)]
    public struct WNDCLASSEX
    {
        public uint cbSize;
        public uint style;
        public IntPtr lpfnWndProc;
        public int cbClsExtra;
        public int cbWndExtra;
        public IntPtr hInstance;
        public IntPtr hIcon;
        public IntPtr hCursor;
        public IntPtr hbrBackground;
        public string lpszMenuName;
        public string lpszClassName;
        public IntPtr hIconSm;
    }

    [StructLayout(LayoutKind.Sequential)]
    public struct RAWINPUTDEVICE
    {
        public ushort usUsagePage;
        public ushort usUsage;
        public uint dwFlags;
        public IntPtr hwndTarget;
    }

    [StructLayout(LayoutKind.Sequential)]
    public struct RAWINPUTHEADER
    {
        public uint dwType;
        public uint dwSize;
        public IntPtr hDevice;
        public IntPtr wParam;
    }

    [StructLayout(LayoutKind.Sequential)]
    public struct RAWHID
    {
        public uint dwSizeHid;
        public uint dwCount;
    }

    [StructLayout(LayoutKind.Sequential)]
    public struct MSG
    {
        public IntPtr hwnd;
        public uint message;
        public IntPtr wParam;
        public IntPtr lParam;
        public uint time;
        public POINT pt;
    }

    [StructLayout(LayoutKind.Sequential)]
    public struct POINT
    {
        public int x;
        public int y;
    }

}

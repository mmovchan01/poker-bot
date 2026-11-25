#ifndef UNICODE
#define UNICODE
#endif
#ifndef _UNICODE
#define _UNICODE
#endif
#define NOMINMAX
#include <windows.h>
#include <gdiplus.h>
#include <shellapi.h>
#include <fcntl.h>
#include <io.h>
#include <cstdio>

#include <algorithm>
#include <filesystem>
#include <iostream>
#include <limits>
#include <string>
#include <vector>

#pragma comment(lib, "gdiplus.lib")
#pragma comment(lib, "shell32.lib")

namespace fs = std::filesystem;

struct WindowInfo {
    HWND handle;
    std::wstring title;
};

BOOL CALLBACK collect_windows(HWND handle, LPARAM parameter) {
    if (!IsWindowVisible(handle) || GetWindow(handle, GW_OWNER) != nullptr) return TRUE;
    const int length = GetWindowTextLengthW(handle);
    if (length == 0) return TRUE;
    std::vector<wchar_t> title(static_cast<size_t>(length) + 1);
    if (!GetWindowTextW(handle, title.data(), static_cast<int>(title.size()))) return TRUE;
    auto* windows = reinterpret_cast<std::vector<WindowInfo>*>(parameter);
    windows->push_back({handle, title.data()});
    return TRUE;
}

bool png_encoder(CLSID& encoder) {
    UINT count = 0, bytes = 0;
    if (Gdiplus::GetImageEncodersSize(&count, &bytes) != Gdiplus::Ok || !bytes) return false;
    std::vector<BYTE> buffer(bytes);
    auto* info = reinterpret_cast<Gdiplus::ImageCodecInfo*>(buffer.data());
    if (Gdiplus::GetImageEncoders(count, bytes, info) != Gdiplus::Ok) return false;
    for (UINT i = 0; i < count; ++i) {
        if (info[i].MimeType && std::wstring(info[i].MimeType) == L"image/png") {
            encoder = info[i].Clsid;
            return true;
        }
    }
    return false;
}

bool capture(HWND window, const fs::path& directory, const CLSID& encoder) {
    if (!IsWindow(window)) {
        std::wcerr << L"Окно закрыто. Перезапустите программу и выберите окно снова.\n";
        return false;
    }
    if (IsIconic(window)) {
        std::wcerr << L"Окно свёрнуто. Разверните его перед снимком.\n";
        return false;
    }
    RECT bounds{};
    if (!GetWindowRect(window, &bounds)) {
        std::wcerr << L"Не удалось получить размер окна.\n";
        return false;
    }
    const int width = bounds.right - bounds.left, height = bounds.bottom - bounds.top;
    if (width <= 0 || height <= 0) return false;
    HDC screen = GetDC(nullptr);
    if (!screen) return false;
    HDC memory = CreateCompatibleDC(screen);
    HBITMAP bitmap = memory ? CreateCompatibleBitmap(screen, width, height) : nullptr;
    bool success = false;
    if (memory && bitmap) {
        HGDIOBJ previous = SelectObject(memory, bitmap);
        if (previous && previous != HGDI_ERROR) {
            // Захват видимых пикселей экрана, включая рамку окна; перекрытия также попадут в кадр.
            if (BitBlt(memory, 0, 0, width, height, screen, bounds.left, bounds.top, SRCCOPY | CAPTUREBLT)) {
                SYSTEMTIME now{};
                GetLocalTime(&now);
                wchar_t filename[100];
                swprintf_s(filename, L"screen_%04u%02u%02u_%02u%02u%02u_%03u_%llu.png",
                    now.wYear, now.wMonth, now.wDay, now.wHour, now.wMinute, now.wSecond, now.wMilliseconds,
                    static_cast<unsigned long long>(GetTickCount64()));
                const fs::path path = directory / filename;
                // GDI+ должен закончить работу с HBITMAP до удаления объекта GDI.
                Gdiplus::Bitmap image(bitmap, nullptr);
                success = image.GetLastStatus() == Gdiplus::Ok && image.Save(path.c_str(), &encoder, nullptr) == Gdiplus::Ok;
                if (success) std::wcout << L"Сохранено: " << path.wstring() << L"\n";
            }
            SelectObject(memory, previous);
        }
    }
    if (bitmap) DeleteObject(bitmap);
    if (memory) DeleteDC(memory);
    ReleaseDC(nullptr, screen);
    if (!success) std::wcerr << L"Не удалось сохранить снимок. Проверьте доступ к экрану и папке.\n";
    return success;
}

int wmain() {
    // Unicode-режим CRT позволяет выводить русские строки и имена окон в консоль.
    _setmode(_fileno(stdout), _O_U16TEXT);
    _setmode(_fileno(stderr), _O_U16TEXT);
    _setmode(_fileno(stdin), _O_U16TEXT);
    // Корректные физические координаты на дисплеях с масштабированием.
    using SetDpiContext = BOOL(WINAPI*)(HANDLE);
    HMODULE user32 = GetModuleHandleW(L"user32.dll");
    auto set_dpi = reinterpret_cast<SetDpiContext>(GetProcAddress(user32, "SetProcessDpiAwarenessContext"));
    if (set_dpi) set_dpi(reinterpret_cast<HANDLE>(-4));  // Per-monitor v2

    Gdiplus::GdiplusStartupInput input;
    ULONG_PTR token = 0;
    if (Gdiplus::GdiplusStartup(&token, &input, nullptr) != Gdiplus::Ok) {
        std::wcerr << L"Ошибка запуска GDI+.\n";
        return 1;
    }
    CLSID encoder{};
    if (!png_encoder(encoder)) {
        std::wcerr << L"PNG-кодировщик недоступен.\n";
        Gdiplus::GdiplusShutdown(token);
        return 1;
    }
    std::vector<WindowInfo> windows;
    EnumWindows(collect_windows, reinterpret_cast<LPARAM>(&windows));
    if (windows.empty()) {
        std::wcerr << L"Открытых окон не найдено.\n";
        Gdiplus::GdiplusShutdown(token);
        return 1;
    }
    std::wcout << L"Выберите окно для снимков:\n";
    for (size_t i = 0; i < windows.size(); ++i) std::wcout << i + 1 << L". " << windows[i].title << L"\n";
    std::wcout << L"Номер окна: " << std::flush;
    size_t choice = 0;
    if (!(std::wcin >> choice) || choice == 0 || choice > windows.size()) {
        std::wcerr << L"Неверный номер окна.\n";
        Gdiplus::GdiplusShutdown(token);
        return 1;
    }
    // Путь относительно exe, а не текущей рабочей папки.
    std::vector<wchar_t> exe_path(32768);
    const DWORD length = GetModuleFileNameW(nullptr, exe_path.data(), static_cast<DWORD>(exe_path.size()));
    if (!length || length >= exe_path.size()) {
        std::wcerr << L"Не удалось определить путь к программе.\n";
        Gdiplus::GdiplusShutdown(token);
        return 1;
    }
    fs::path directory = fs::path(exe_path.data()).parent_path() / L"screenshots";
    std::error_code error;
    fs::create_directories(directory, error);
    if (error) {
        std::wcerr << L"Не удалось создать папку screenshots рядом с программой. Переместите её в доступную папку.\n";
        Gdiplus::GdiplusShutdown(token);
        return 1;
    }
    if (!RegisterHotKey(nullptr, 1, MOD_NOREPEAT, VK_F8)) {
        std::wcerr << L"Горячая клавиша F8 занята другой программой.\n";
        Gdiplus::GdiplusShutdown(token);
        return 1;
    }
    if (!RegisterHotKey(nullptr, 2, MOD_NOREPEAT, VK_F9)) {
        std::wcerr << L"Горячая клавиша F9 занята другой программой.\n";
        UnregisterHotKey(nullptr, 1);
        Gdiplus::GdiplusShutdown(token);
        return 1;
    }
    std::wcout << L"Откройте выбранное окно игры. F8 — снимок, F9 — выход.\n"
               << L"Папка: " << directory.wstring() << L"\n" << std::flush;
    MSG message{};
    while (GetMessageW(&message, nullptr, 0, 0) > 0) {
        if (message.message == WM_HOTKEY) {
            if (message.wParam == 2) break;
            if (message.wParam == 1) capture(windows[choice - 1].handle, directory, encoder);
        }
    }
    UnregisterHotKey(nullptr, 1);
    UnregisterHotKey(nullptr, 2);
    Gdiplus::GdiplusShutdown(token);
    return 0;
}

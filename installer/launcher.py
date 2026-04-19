import os, sys, subprocess
def main():
    appdata = os.environ.get("APPDATA", os.path.expanduser("~"))
    install_dir = os.path.join(appdata, "Finalyse")
    python_exe  = os.path.join(install_dir, "python", "python.exe")
    go_py       = os.path.join(install_dir, "app", "GO.py")
    if not os.path.exists(python_exe) or not os.path.exists(go_py):
        import ctypes
        ctypes.windll.user32.MessageBoxW(0,
            "Installation corrompue.\nReinstallez Finalyse.",
            "Finalyse", 0x10)
        return
    subprocess.Popen([python_exe, go_py],
        cwd=os.path.dirname(go_py),
        creationflags=subprocess.CREATE_NO_WINDOW)
if __name__ == "__main__":
    main()

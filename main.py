import tkinter as tk
from gui import SimulatorApp


def main():
    root = tk.Tk()
    SimulatorApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
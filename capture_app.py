"""학습 영상 퀴즈 캡처 프로그램 (1단계)

Windows 데스크톱에서 실행하는 화면 영역 캡처 도구.
- 메인 창의 "캡처" 버튼을 누르면 전체화면 반투명 오버레이가 뜬다.
- 오버레이 위에서 마우스를 드래그해 사각형 영역을 선택한다.
- 마우스를 떼면 그 영역만 캡처해서 capture/{과목명}_{YYYYMMDD_HHMMSS}.png 로 저장한다.
- ESC 로 선택을 취소한다.

사용법:
    python capture_app.py            # GUI 실행
    python capture_app.py --selftest # GUI 조작 없이 캡처/저장/초기화 검증
"""

import datetime
import os
import sys

import mss
from PIL import Image

CAPTURE_DIR = "capture"


# --------------------------------------------------------------------------- #
# DPI 대응
# --------------------------------------------------------------------------- #
def enable_dpi_awareness():
    """모니터 배율이 100%가 아니어도 Tk 좌표 == 실제 픽셀이 되도록 설정."""
    if sys.platform != "win32":
        return
    import ctypes

    try:
        # Per-Monitor DPI Aware v2
        ctypes.windll.user32.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4))
        return
    except Exception:
        pass
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)  # PROCESS_PER_MONITOR_DPI_AWARE
        return
    except Exception:
        pass
    try:
        ctypes.windll.user32.SetProcessDPIAware()
    except Exception:
        pass


# --------------------------------------------------------------------------- #
# 캡처 / 저장 (GUI 와 무관한 공통 로직)
# --------------------------------------------------------------------------- #
def grab_region(left, top, width, height):
    """지정한 화면 영역을 캡처해서 PIL.Image 로 반환."""
    with mss.MSS() as sct:
        shot = sct.grab({"left": left, "top": top, "width": width, "height": height})
    return Image.frombytes("RGB", shot.size, shot.bgra, "raw", "BGRX")


def sanitize_subject(subject):
    """과목명을 파일명에 쓸 수 있게 정리. 비면 '무제'."""
    subject = (subject or "").strip()
    if not subject:
        return "무제"
    for ch in '\\/:*?"<>|':
        subject = subject.replace(ch, "_")
    return subject


def save_capture(image, subject):
    """PIL.Image 를 capture/{과목명}_{타임스탬프}.png 로 저장하고 경로 반환."""
    os.makedirs(CAPTURE_DIR, exist_ok=True)
    stamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"{sanitize_subject(subject)}_{stamp}.png"
    path = os.path.join(CAPTURE_DIR, filename)
    image.save(path, "PNG")
    return path


# --------------------------------------------------------------------------- #
# GUI
# --------------------------------------------------------------------------- #
class CaptureApp:
    def __init__(self, root):
        self.root = root
        self.root.title("학습 퀴즈 캡처")
        self.root.geometry("360x180")
        self.root.resizable(False, False)

        import tkinter as tk

        pad = {"padx": 12, "pady": 6}

        row = tk.Frame(root)
        row.pack(fill="x", **pad)
        tk.Label(row, text="과목명:").pack(side="left")
        self.subject_var = tk.StringVar()
        self.subject_entry = tk.Entry(row, textvariable=self.subject_var)
        self.subject_entry.pack(side="left", fill="x", expand=True, padx=(6, 0))

        self.capture_btn = tk.Button(
            root, text="캡처", height=2, command=self.start_capture
        )
        self.capture_btn.pack(fill="x", **pad)

        self.status_var = tk.StringVar(value="준비됨. 과목명을 입력하고 [캡처]를 누르세요.")
        self.status_label = tk.Label(
            root, textvariable=self.status_var, anchor="w", justify="left",
            wraplength=336, fg="#333",
        )
        self.status_label.pack(fill="x", **pad)

        # 오버레이 상태
        self.overlay = None
        self.canvas = None
        self.start_x = self.start_y = 0
        self.rect_id = None

    def log(self, msg):
        self.status_var.set(msg)
        print(f"[capture_app] {msg}")
        self.root.update_idletasks()

    # --- 오버레이 흐름 ---------------------------------------------------- #
    def start_capture(self):
        import tkinter as tk

        subject = self.subject_var.get().strip()
        if not subject:
            self.log("과목명이 비어 있어 '무제'로 저장됩니다. 드래그로 영역을 선택하세요.")
        else:
            self.log(f"'{subject}' 캡처 중 - 드래그로 영역 선택, ESC로 취소.")

        self.root.withdraw()  # 메인 창을 캡처에 안 찍히게 숨김
        self.root.after(120, self._build_overlay)

    def _build_overlay(self):
        import tkinter as tk

        self.overlay = tk.Toplevel(self.root)
        self.overlay.attributes("-fullscreen", True)
        self.overlay.attributes("-alpha", 0.30)
        self.overlay.attributes("-topmost", True)
        self.overlay.configure(bg="gray20", cursor="crosshair")

        self.canvas = tk.Canvas(
            self.overlay, bg="gray20", highlightthickness=0, cursor="crosshair"
        )
        self.canvas.pack(fill="both", expand=True)

        self.canvas.bind("<ButtonPress-1>", self._on_press)
        self.canvas.bind("<B1-Motion>", self._on_drag)
        self.canvas.bind("<ButtonRelease-1>", self._on_release)
        self.overlay.bind("<Escape>", self._on_cancel)

        self.overlay.focus_force()
        self.rect_id = None

    def _on_press(self, event):
        self.start_x, self.start_y = event.x, event.y
        if self.rect_id is not None:
            self.canvas.delete(self.rect_id)
        self.rect_id = self.canvas.create_rectangle(
            self.start_x, self.start_y, self.start_x, self.start_y,
            outline="#00b4ff", width=2, fill="",
        )

    def _on_drag(self, event):
        if self.rect_id is not None:
            self.canvas.coords(
                self.rect_id, self.start_x, self.start_y, event.x, event.y
            )

    def _on_release(self, event):
        left = int(min(self.start_x, event.x))
        top = int(min(self.start_y, event.y))
        right = int(max(self.start_x, event.x))
        bottom = int(max(self.start_y, event.y))
        width, height = right - left, bottom - top

        # 오버레이의 화면상 위치를 더해 절대 좌표로 변환 (fullscreen 이면 대개 0,0)
        ox = self.overlay.winfo_rootx()
        oy = self.overlay.winfo_rooty()
        abs_left, abs_top = left + ox, top + oy

        self._teardown_overlay()

        if width < 3 or height < 3:
            self.root.deiconify()
            self.log("선택 영역이 너무 작습니다. 다시 [캡처]를 눌러 시도하세요.")
            return

        # 오버레이가 화면에서 완전히 사라진 뒤 캡처
        self.root.after(120, lambda: self._do_grab(abs_left, abs_top, width, height))

    def _do_grab(self, left, top, width, height):
        try:
            image = grab_region(left, top, width, height)
            path = save_capture(image, self.subject_var.get())
        except Exception as exc:  # noqa: BLE001
            self.root.deiconify()
            self.log(f"캡처 실패: {exc!r}")
            return
        self.root.deiconify()
        self.log(f"저장됨: {os.path.abspath(path)}  ({width}x{height})")

    def _on_cancel(self, event=None):
        self._teardown_overlay()
        self.root.deiconify()
        self.log("취소됨 (ESC).")

    def _teardown_overlay(self):
        if self.overlay is not None:
            try:
                self.overlay.destroy()
            except Exception:
                pass
        self.overlay = None
        self.canvas = None
        self.rect_id = None


# --------------------------------------------------------------------------- #
# 셀프테스트 (GUI 조작 없이 로그로 검증)
# --------------------------------------------------------------------------- #
def selftest():
    print("=== capture_app selftest ===")
    print(f"python   : {sys.version.split()[0]}  ({sys.platform})")
    print(f"cwd      : {os.getcwd()}")
    import mss as _mss

    print(f"mss      : {_mss.__version__}")
    print(f"pillow   : {Image.__version__ if hasattr(Image, '__version__') else 'n/a'}")

    # 1) capture/ 폴더 생성
    os.makedirs(CAPTURE_DIR, exist_ok=True)
    print(f"[1] capture dir  : {os.path.abspath(CAPTURE_DIR)}  exists={os.path.isdir(CAPTURE_DIR)}")

    # 2) 화면 좌상단 고정 영역 실제 캡처
    region = (0, 0, 300, 200)
    image = grab_region(*region)
    print(f"[2] grabbed      : region={region}  image.size={image.size}  mode={image.mode}")

    # 3) 파일명 규칙대로 저장
    path = save_capture(image, "셀프테스트")
    ok = os.path.isfile(path)
    size = os.path.getsize(path) if ok else -1
    print(f"[3] saved        : {os.path.abspath(path)}")
    print(f"    exists={ok}  bytes={size}")
    fname = os.path.basename(path)
    rule_ok = fname.startswith("셀프테스트_") and fname.endswith(".png") and len(fname) == len("셀프테스트_") + 15 + 4
    print(f"    filename rule : {fname}  -> {'OK' if rule_ok else 'MISMATCH'}")

    # 4) GUI 초기화 (mainloop 없이)
    try:
        import tkinter as tk

        root = tk.Tk()
        app = CaptureApp(root)
        root.update()  # 위젯 실제 생성
        widgets_ok = bool(app.capture_btn and app.subject_entry and app.status_label)
        root.destroy()
        print(f"[4] GUI init     : OK  (widgets_ok={widgets_ok})")
    except Exception as exc:  # noqa: BLE001
        print(f"[4] GUI init     : FAILED  {exc!r}")
        return 1

    all_ok = ok and rule_ok and widgets_ok and size > 0
    print(f"=== result: {'PASS' if all_ok else 'FAIL'} ===")
    return 0 if all_ok else 1


# --------------------------------------------------------------------------- #
def main():
    enable_dpi_awareness()

    if "--selftest" in sys.argv:
        raise SystemExit(selftest())

    import tkinter as tk

    root = tk.Tk()
    CaptureApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()

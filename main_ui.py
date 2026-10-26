# coding:utf-8
import _thread
import os
os.chdir(os.path.dirname(os.path.abspath(__file__)))  # 切换到脚本目录（img/ 相对路径依赖）
import tkinter as tk
import tkinter.font as tkFont
from tkinter import messagebox, ttk

from PIL import Image, ImageTk

import utils
from download_paper_by_URLfile import organize_info_by_txt
from utils import downLoad_paper


def show_confirm(message=""):
    return messagebox.askyesno("确认框", message)


def error_inform(message=""):
    return messagebox.showerror("参数错误", message)


def show_succeed_window(message=""):
    return messagebox.showinfo("下载成功！", message)


def show_fail_window(message=""):
    return messagebox.showerror("下载失败...", message)


def image_label(frame, img, width, height, **kw):
    """把图片拉伸到 width x height 像素后贴进 Label，其余关键字参数透传给 Label。"""
    _img = Image.open(img) if isinstance(img, str) else img
    tk_img = ImageTk.PhotoImage(_img.resize((width, height), Image.LANCZOS))
    lbl = tk.Label(frame, image=tk_img, width=width, height=height, bd=0,
                   padx=0, pady=0, highlightthickness=0, relief="flat", **kw)
    lbl.image = tk_img  # 挂个引用挡住 GC，否则 PhotoImage 被回收后 Label 变空白
    return lbl


def attach_fulltext_tip(widget):
    """单行 Text 只能露出一段内容，长路径会把开头滚掉；鼠标停上去时用无边框小窗显示全文。"""
    state = {'tip': None}

    def hide(_e=None):
        if state['tip'] is not None:
            state['tip'].destroy()
            state['tip'] = None

    def show(_e=None):
        hide()
        text = widget.get('1.0', 'end').strip()
        if not text:
            return
        tip = tk.Toplevel(widget)
        tip.wm_overrideredirect(True)
        tip.attributes('-topmost', True)
        tk.Label(tip, text=text, bg='#ffffe0', fg='black', relief='solid', bd=1,
                 font=('微软雅黑', 9), padx=6, pady=2).pack()
        widget.update_idletasks()
        tip.wm_geometry('+%d+%d' % (widget.winfo_rootx(),
                                    widget.winfo_rooty() + widget.winfo_height() + 4))
        state['tip'] = tip

    widget.bind('<Enter>', show)
    widget.bind('<Leave>', hide)
    widget.bind('<KeyRelease>', hide)
    return state


def set_sharp_window_icon(root, ico_path):
    """按 DPI 的真实像素尺寸从 .ico 取对应帧，再 WM_SETICON 设置窗口图标。

    iconbitmap 只取目录第一帧，任务栏槽位按 DPI 需要 36~48px，靠它会被放大。
    """
    import ctypes
    from ctypes import wintypes
    user32 = ctypes.windll.user32
    root.update_idletasks()
    user32.GetParent.restype = wintypes.HWND
    user32.GetParent.argtypes = [wintypes.HWND]
    hwnd = user32.GetParent(root.winfo_id())
    if not hwnd:
        return False
    user32.LoadImageW.restype = ctypes.c_void_p
    user32.LoadImageW.argtypes = [wintypes.HINSTANCE, wintypes.LPCWSTR, ctypes.c_uint,
                                  ctypes.c_int, ctypes.c_int, ctypes.c_uint]
    user32.SendMessageW.argtypes = [wintypes.HWND, ctypes.c_uint, wintypes.WPARAM, wintypes.LPARAM]
    IMAGE_ICON, LR_LOADFROMFILE = 1, 0x00000010
    # 下限 48/32：万一进程不是 DPI 感知、度量回落到 32/16，也能拿到高分辨率帧交给 Windows 向下采样
    big = max(user32.GetSystemMetrics(11), 48)     # SM_CXICON
    small = max(user32.GetSystemMetrics(49), 32)   # SM_CXSMICON
    h_big = user32.LoadImageW(None, ico_path, IMAGE_ICON, big, big, LR_LOADFROMFILE)
    if not h_big:
        return False
    h_small = user32.LoadImageW(None, ico_path, IMAGE_ICON, small, small, LR_LOADFROMFILE)
    WM_SETICON, ICON_BIG, ICON_SMALL = 0x0080, 1, 0
    user32.SendMessageW(hwnd, WM_SETICON, ICON_BIG, h_big)
    if h_small:
        user32.SendMessageW(hwnd, WM_SETICON, ICON_SMALL, h_small)
    return True


def check_value_valid(save_dir=None, url_path=None):
    if not (save_dir and url_path):
        error_inform("请检查 论文保存文件夹 URL文件路径 是否已输入")
        return False
    return True



class App:
    def __init__(self):
        self.root = tk.Tk()
        # 设置窗口/任务栏图标：给本进程独立 AppUserModelID，避免被归到 pythonw 组而显示 Python 图标
        try:
            import ctypes
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("IEEE.CNKI.Downloader.v2")
        except Exception:
            pass
        _ico = os.path.join(os.path.dirname(os.path.abspath(__file__)), "img", "app-icon-rounded.ico")
        try:
            self.root.iconbitmap(_ico)
        except Exception as e:
            print("icon set failed:", e)
        try:
            if not set_sharp_window_icon(self.root, _ico):
                print("icon set failed: LoadImage/GetParent 未取到句柄")
        except Exception as e:
            print("icon set failed:", e)
        self.root.title("文献批量下载 v2.1")
        self.no_title = False
        self.show_title()
        self.body()
        self.fit_to_screen()  # 按去掉任务栏的工作区定位，保证底部按钮可见、不被任务栏遮挡
        self.fail_list = []
        self.paper_info = {}
        self.stat = {'ok': 0, 'fail': 0, 'exist': 0, 'total': 0}
        self.downloading = False

    def fit_to_screen(self):
        """按去掉任务栏后的工作区摆放窗口：水平居中、靠上，保证整窗（含底部按钮）不被任务栏遮挡。"""
        try:
            self.root.update_idletasks()
        except Exception:
            pass
        wl = wt = 0
        wr = self.root.winfo_screenwidth()
        wb = self.root.winfo_screenheight()
        try:
            import ctypes
            from ctypes import wintypes
            rect = wintypes.RECT()
            # SPI_GETWORKAREA = 0x0030：不含任务栏的可用区域
            if ctypes.windll.user32.SystemParametersInfoW(0x0030, 0, ctypes.byref(rect), 0):
                wl, wt, wr, wb = rect.left, rect.top, rect.right, rect.bottom
        except Exception:
            pass
        work_w = max(1, wr - wl)
        work_h = max(1, wb - wt)
        req_w = self.root.winfo_reqwidth()
        req_h = self.root.winfo_reqheight()
        w = min(req_w, work_w)
        h = min(req_h, work_h)
        x = wl + max(0, (work_w - w) // 2)
        y = wt + max(0, (work_h - h) // 4)
        if y + h > wb:          # 兜底：贴到工作区底部之上
            y = max(wt, wb - h)
        self.root.geometry("%dx%d+%d+%d" % (w, h, x, y))

    def body(self):
        # 标题栏：Frame 整条铺 Teal，标题 Label 只有一行高，上下由 Frame 底色补齐
        f1 = tk.Frame(self.root, bg="Teal")
        im1 = image_label(f1, "img/root.ico", 76, 76, bg="Teal")
        im1.bind('<Button-1>', self.show_title)
        im1.pack(side=tk.LEFT, anchor=tk.NW, fill=tk.Y)

        ft1 = tkFont.Font(family="微软雅黑", size=22, weight=tkFont.BOLD)
        tk.Label(f1, text="文献批量下载_v2.1", height=1, fg="white", font=ft1, bg="Teal") \
            .pack(side=tk.LEFT, expand=tk.YES, fill=tk.X)

        im2 = image_label(f1, "img/exit.ico", 76, 76, bg="Teal")
        im2.bind('<Button-1>', self.close)
        im2.pack(side=tk.RIGHT, anchor=tk.NW, fill=tk.Y)

        f2 = tk.Frame(self.root)
        image_label(f2, "img/ieee.png", 390, 132).pack(side=tk.LEFT, padx=(16, 4), pady=2)
        image_label(f2, "img/cnki.png", 390, 132).pack(side=tk.LEFT, padx=(4, 16), pady=2)
        f1.pack(fill=tk.X)
        f2.pack()

        ft_title = tkFont.Font(family="微软雅黑", size=13, weight=tkFont.BOLD)
        ft_middle = tkFont.Font(family="微软雅黑", size=11)
        ft = tkFont.Font(family="微软雅黑", size=13)

        f_src = tk.Frame(self.root)
        tk.Label(f_src, text="下载来源 ", font=ft, anchor='w').pack(side='left', padx=20)
        self.src_var = tk.StringVar(value="ieee")
        tk.Radiobutton(f_src, text="IEEE Xplore", font=ft_middle, variable=self.src_var,
                       value="ieee").pack(side='left')
        tk.Radiobutton(f_src, text="知网 CNKI", font=ft_middle, variable=self.src_var,
                       value="cnki").pack(side='left', padx=12)
        f_src.pack(fill='both', expand=True)

        f3 = tk.Frame(self.root)
        tk.Label(f3, text="论文保存文件夹 ", font=ft, anchor='w').pack(side='left', padx=20)
        self.save_dir = tk.Text(f3, bg="white", font=ft, height=1, width=28)
        self.save_dir.pack(side=tk.LEFT)
        attach_fulltext_tip(self.save_dir)
        tk.Button(f3, text="浏览...", width=8, font=ft_middle, bg="lightblue",
                  command=self.browse_save_dir).pack(side=tk.LEFT, padx=6)
        f3.pack(fill='both', expand=True)

        f_urltxt = tk.Frame(self.root)
        tk.Label(f_urltxt, text="URL文件路径", font=ft, anchor='w', padx=20).pack(side=tk.LEFT)
        self.url_txt_path = tk.Text(f_urltxt, bg="white", font=ft, height=1, width=24)
        self.url_txt_path.pack(side=tk.LEFT)
        attach_fulltext_tip(self.url_txt_path)
        tk.Button(f_urltxt, text="浏览...", width=8, font=ft_middle, bg="lightblue",
                  command=self.browse_url_file).pack(side=tk.LEFT, padx=6)
        tk.Button(f_urltxt, text="开始下载", width=10, height=1, bg="cadetblue", font=ft, command=self.begin_download_src) \
            .pack(side=tk.LEFT, anchor=tk.W, padx=12)
        tk.Label(f_urltxt, text="", font=ft).pack(side=tk.LEFT)
        f_urltxt.pack(fill='both', expand=True)
        f9 = tk.Frame(self.root)
        self.CheckVar1 = tk.IntVar()
        self.save_with_yesr_1 = tk.Checkbutton(f9, text="论文保存时自动添加年份前缀", font=ft_middle, variable=self.CheckVar1,
                                               onvalue=1, offvalue=0)
        self.save_with_yesr_1.pack(side=tk.LEFT, padx=20)
        f9.pack(fill='both', expand=True)

        # ============ 下载面板（内嵌：统计+进度+队列+日志+操作） ============
        panel = tk.LabelFrame(self.root, text="下载监控面板", font=ft_title, padx=8, pady=4)
        panel.pack(fill=tk.BOTH, expand=True, padx=10, pady=2)

        # ⑩ 操作按钮（独立于面板，始终显示）
        btns = tk.Frame(self.root)
        btns.pack(fill=tk.X, padx=14, pady=(0, 5))
        self.btn_retry = tk.Button(btns, text="重试失败", width=14, bg="orange", font=ft_middle,
                                   command=self.retry_failed, state="disabled")
        self.btn_retry.pack(side=tk.LEFT, padx=5, ipady=3)
        tk.Button(btns, text="打开保存文件夹", width=18, bg="lightgreen", font=ft_middle,
                  command=self.open_folder).pack(side=tk.LEFT, padx=5, ipady=3)
        self.btn_clear = tk.Button(btns, text="清空日志", width=12, font=ft_middle,
                                   command=self.clear_log)
        self.btn_clear.pack(side=tk.LEFT, padx=5, ipady=3)

        # ⑧ 统计徽标
        self.stat_var = tk.StringVar(value="成功 0 | 失败 0 | 已存在 0 | 总数 0")
        tk.Label(panel, textvariable=self.stat_var, font=ft_middle, fg="blue", anchor='w').pack(fill=tk.X)

        # ⑥ 进度条 + 文本
        self.download_pb = ttk.Progressbar(panel, length=500, mode="determinate", orient=tk.HORIZONTAL)
        self.download_pb.pack(fill=tk.X, pady=3)
        self.pb_label = tk.Label(panel, text="等待下载...", font=ft_middle, anchor='w')
        self.pb_label.pack(fill=tk.X)

        # ⑨ 队列表 + ⑦ 日志区（左右分栏）
        mid = tk.Frame(panel)
        mid.pack(fill=tk.BOTH, expand=True, pady=4)

        # 队列表（左）
        left = tk.LabelFrame(mid, text="下载队列", font=ft_middle)
        left.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(0, 4))
        self.tree = ttk.Treeview(left, columns=("status", "file"), show="headings", height=2)
        self.tree.heading("status", text="状态")
        self.tree.heading("file", text="文件名")
        self.tree.column("status", width=70, anchor="center")
        self.tree.column("file", width=300)
        tsb = ttk.Scrollbar(left, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=tsb.set)
        self.tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        tsb.pack(side=tk.RIGHT, fill=tk.Y)

        # 日志区（右）
        right = tk.LabelFrame(mid, text="实时日志", font=ft_middle)
        right.pack(side=tk.RIGHT, fill=tk.BOTH, expand=True)
        self.log_text = tk.Text(right, height=4, width=40, state="disabled", font=("Consolas", 9))
        lsb = ttk.Scrollbar(right, orient="vertical", command=self.log_text.yview)
        self.log_text.configure(yscrollcommand=lsb.set)
        self.log_text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        lsb.pack(side=tk.RIGHT, fill=tk.Y)

    # ---------- 面板工具 ----------
    def log(self, msg):
        self.log_text.configure(state="normal")
        self.log_text.insert(tk.END, msg + "\n")
        self.log_text.see(tk.END)
        self.log_text.configure(state="disabled")

    def update_stat(self):
        s = self.stat
        self.stat_var.set("成功 {} | 失败 {} | 已存在 {} | 总数 {}".format(s['ok'], s['fail'], s['exist'], s['total']))

    def set_queue_status(self, i, status):
        if hasattr(self, 'tree') and self.tree.get_children():
            try:
                item = self.tree.get_children()[i]
                self.tree.set(item, "status", status)
            except Exception:
                pass

    def reset_panel(self):
        self.stat = {'ok': 0, 'fail': 0, 'exist': 0, 'total': 0}
        self.update_stat()
        self.download_pb["value"] = 0
        self.pb_label.config(text="等待下载...")
        if hasattr(self, 'tree'):
            self.tree.delete(*self.tree.get_children())

    def prepare_panel(self, labels, note):
        """重置统计与队列，再把待下载条目一次性填进去（IEEE / 知网两条流程共用）"""
        self.fail_list = []
        self.reset_panel()
        total = len(labels)
        self.stat['total'] = total
        self.update_stat()
        self.download_pb["maximum"] = total
        for text in labels:
            self.tree.insert("", tk.END, values=("⏳待下载", text[:50]))
        self.pb_label.config(text=note)

    # ---------- 下载流程 ----------
    def on_item_callback(self, i, total, status, fname, err=""):
        """下载循环回调：更新队列/日志/统计"""
        self.stat['total'] = total
        if status == 'ok':
            self.stat['ok'] += 1
            self.log("[OK] {}".format(fname[:60]))
        elif status == 'exist':
            self.stat['exist'] += 1
        elif status == 'fail':
            self.stat['fail'] += 1
            self.log("[FAIL] {} | {}".format(fname[:55], err[:40]))
            self.fail_list.append(fname)
        self.update_stat()
        self.set_queue_status(i, {"ok": "✅成功", "fail": "❌失败", "exist": "⏭已存在"}.get(status, status))

    def create_progress_bar(self, paper_info):
        """初始化下载面板（内嵌，不再弹独立窗口）"""
        self.paper_info = paper_info
        total = len(paper_info)
        self.prepare_panel([os.path.basename(paper_info[k]['name']) for k in sorted(paper_info)],
                           "准备下载 0/{} (0%)".format(total))
        self.log("开始下载，共 {} 篇 -> {}".format(total, os.path.dirname(paper_info[0]['name'])))

    def refresh_window(self):
        if not hasattr(self, 'download_pb'):
            return
        total = self.download_pb["maximum"]
        while utils.get_value("progress_bar_num") < total - 1:
            cur = utils.get_value("progress_bar_num")
            self.download_pb["value"] = cur
            pct = int(cur / total * 100) if total else 0
            fname = ''
            if cur in self.paper_info:
                fname = os.path.basename(self.paper_info[cur]['name'])
            self.pb_label.config(text="正在下载 {}/{} ({}%)\n{}".format(cur + 1, total, pct, fname[:40]))
            self.root.update()
        # 收尾
        self.download_pb["value"] = total
        self.pb_label.config(text="完成 {}/{} (100%)".format(total, total))

    def download_1_thread(self):
        try:
            self._download_1_core()
        except Exception as e:
            import traceback
            traceback.print_exc()
            show_fail_window("下载出错: %s" % str(e)[:120])

    def _download_1_core(self):
        if show_confirm("开始下载吗？"):
            save_dir = self.save_dir.get(0.0, tk.END).split("\n")[0].strip()
            url_txt_path = self.url_txt_path.get(0.0, tk.END).split("\n")[0].strip()
            save_with_year = self.CheckVar1.get()
            is_valid = check_value_valid(save_dir, url_txt_path)
            if not is_valid:
                return
            if not os.path.exists(save_dir):
                os.mkdir(save_dir)
            status, paper_info = organize_info_by_txt(save_dir, url_txt_path, paper_name_with_year=save_with_year)
            if not status:
                show_fail_window("URL文件未找到...")
                return
            if not paper_info:
                show_fail_window("文件中没有可下载的条目。\n请确认 txt 是 IEEE 导出的含 URL 行的格式（方法1）")
                return
            if self.all_downloaded(paper_info):
                info = "{}篇论文已存在，无需下载!".format(len(paper_info))
                show_succeed_window(info)
                return
            self.create_progress_bar(paper_info)
            try:
                _thread.start_new_thread(self.refresh_window, ())
            except:
                show_fail_window("Error: 无法启动线程")
            succeed, paper_downloaded, already_exist = downLoad_paper(paper_info, callback=self.on_item_callback)
            self.btn_retry.configure(state="normal" if self.fail_list else "disabled")
            if succeed:
                info = "成功下载{}篇论文！".format(paper_downloaded + already_exist)
                show_succeed_window(info)
            else:
                show_fail_window("部分下载失败，可点击「重试失败」重新下载。")

    def begin_download_src(self):
        """按下载来源分派"""
        if getattr(self, 'src_var', None) and self.src_var.get() == 'cnki':
            self.begin_download_cnki()
        else:
            self.begin_download_1()

    def begin_download_cnki(self):
        try:
            _thread.start_new_thread(self._cnki_thread, ())
        except:
            show_fail_window("Error: 无法启动线程")

    def _cnki_thread(self):
        try:
            self._cnki_core()
        except Exception as e:
            import traceback
            traceback.print_exc()
            show_fail_window("知网下载出错: %s" % str(e)[:120])

    def _cnki_core(self):
        """知网批量下载（浏览器自动化，需 cnki_cookie.txt）"""
        if not show_confirm("开始下载吗？"):
            return
        save_dir = self.save_dir.get(0.0, tk.END).split("\n")[0].strip()
        list_path = self.url_txt_path.get(0.0, tk.END).split("\n")[0].strip()
        if not (save_dir and list_path):
            error_inform("请填写 论文保存文件夹 和 清单文件路径\n（知网清单: 每行 题名<TAB>作者<TAB>年份）")
            return
        import cnki_core
        if not os.path.exists(cnki_core.COOKIE_FILE):
            show_fail_window("缺少 cnki_cookie.txt（知网登录凭证）。\n准备：浏览器登录 www.cnki.net -> F12 -> Network -> 复制 Cookie -> 保存为 cnki_cookie.txt")
            return
        rows = cnki_core.parse_list(list_path)
        if not rows:
            show_fail_window("清单为空或格式不对（每行: 题名<TAB>作者<TAB>年份）")
            return
        if not os.path.isdir(save_dir):
            os.makedirs(save_dir, exist_ok=True)
        self._cnki_rows = rows
        self.prepare_panel([r[0] for r in rows], "知网模式准备下载 0/{}".format(len(rows)))
        self.log("知网模式（浏览器自动化）：清单 {} 篇 -> {}".format(len(rows), save_dir))
        ok_cnt, fail_list = cnki_core.run_batch(rows, save_dir,
                                                callback=self.on_item_callback,
                                                log=self.log)
        total = len(rows)
        self.download_pb["value"] = total
        self.pb_label.config(text="完成 {}/{}".format(self.stat['ok'] + self.stat['exist'], total))
        self.btn_retry.configure(state="normal" if fail_list else "disabled")
        if fail_list:
            show_fail_window("知网下载完成：成功 {} / {}，失败 {} 篇（见日志与失败清单）".format(
                ok_cnt, total, len(fail_list)))
        else:
            show_succeed_window("知网下载完成：成功 {} 篇！".format(ok_cnt))

    def begin_download_1(self):
        try:
            _thread.start_new_thread(self.download_1_thread, ())
        except:
            show_fail_window("Error: 无法启动线程")

    def all_downloaded(self, paperlist):
        for key, value in paperlist.items():
            if not os.path.exists(value['name']):
                return False
        return True

    # ---------- ⑩ 重试失败 ----------
    def retry_failed(self):
        if not self.fail_list:
            return
        if not show_confirm("重新下载 {} 篇失败文献吗？".format(len(self.fail_list))):
            return
        save_dir = self.save_dir.get(0.0, tk.END).split("\n")[0].strip()
        if getattr(self, 'src_var', None) and self.src_var.get() == 'cnki' and hasattr(self, '_cnki_rows'):
            # 知网模式：用失败标题重跑
            fail_titles = set(os.path.basename(f)[:-4] if f.endswith('.pdf') else f
                              for f in self.fail_list)
            rows = [r for r in self._cnki_rows if r[0] in fail_titles or any(r[0] in t for t in fail_titles)]
            if not rows:
                return
            self.prepare_panel([r[0] for r in rows], "知网重试 0/{}".format(len(rows)))
            self.log("知网重试 {} 篇".format(len(rows)))
            # 这里不能起 refresh_window：它读 IEEE 侧的共享进度变量，知网流程不更新该值
            _thread.start_new_thread(self.retry_failed_cnki_thread, (rows, save_dir))
            return
        retry_info = {}
        idx = 0
        for k, v in self.paper_info.items():
            if v['name'] in self.fail_list:
                retry_info[idx] = v
                idx += 1
        if not retry_info:
            return
        self.create_progress_bar(retry_info)
        try:
            _thread.start_new_thread(self.refresh_window, ())
        except:
            pass
        _thread.start_new_thread(self.retry_failed_thread, (retry_info,))

    def retry_failed_thread(self, retry_info):
        try:
            succeed, _, _ = downLoad_paper(retry_info, callback=self.on_item_callback)
            self.btn_retry.configure(state="normal" if self.fail_list else "disabled")
            if succeed:
                show_succeed_window("重试完成，全部成功！")
            else:
                show_fail_window("重试完成，仍有失败项，可再次点击重试")
        except Exception as e:
            self.log("重试异常: {}".format(e))

    def retry_failed_cnki_thread(self, rows, save_dir):
        try:
            import cnki_core
            ok_cnt, fail_list = cnki_core.run_batch(rows, save_dir,
                                                    callback=self.on_item_callback,
                                                    log=self.log)
            self.download_pb["value"] = len(rows)
            self.pb_label.config(text="完成 {}/{}".format(self.stat['ok'] + self.stat['exist'], len(rows)))
            self.btn_retry.configure(state="normal" if fail_list else "disabled")
            if fail_list:
                show_fail_window("重试完成：成功 {}，仍有 {} 篇失败".format(ok_cnt, len(fail_list)))
            else:
                show_succeed_window("重试完成，全部成功！")
        except Exception as e:
            self.log("知网重试异常: {}".format(e))

    def open_folder(self):
        save_dir = self.save_dir.get(0.0, tk.END).split("\n")[0].strip()
        if save_dir and os.path.isdir(save_dir):
            os.startfile(save_dir)
        else:
            show_fail_window("保存文件夹不存在或未填写")

    def clear_log(self):
        self.log_text.configure(state="normal")
        self.log_text.delete(1.0, tk.END)
        self.log_text.configure(state="disabled")

    def browse_save_dir(self):
        from tkinter import filedialog
        d = filedialog.askdirectory(title="选择论文保存文件夹")
        if d:
            self.save_dir.delete(1.0, tk.END)
            self.save_dir.insert(1.0, d)

    def browse_url_file(self):
        from tkinter import filedialog
        f = filedialog.askopenfilename(title="选择 URL 文件（.txt）",
                                       filetypes=[("文本文件", "*.txt"), ("所有文件", "*.*")])
        if f:
            self.url_txt_path.delete(1.0, tk.END)
            self.url_txt_path.insert(1.0, f)

    def show_title(self, *args):
        self.root.overrideredirect(self.no_title)
        self.no_title = not self.no_title

    def close(self, *arg):
        if show_confirm("确认退出吗 ?"):
            self.root.destroy()


if __name__ == "__main__":
    utils._init()
    utils.set_value("progress_bar_num", 0)
    app = App()
    app.root.mainloop()

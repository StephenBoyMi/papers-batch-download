# -*- coding: utf-8 -*-
"""重建「文献批量下载」开始菜单快捷方式（自适应当前位置）。

整个文件夹换到新位置后，双击运行本脚本即可让快捷方式跟到新路径。
"""
import os
import subprocess
import sys

BASE = os.path.dirname(os.path.abspath(__file__))
MAIN = os.path.join(BASE, 'main_ui.py')
ICO = os.path.join(BASE, 'img', 'app-icon-rounded.ico')
LNK_NAME = '文献批量下载.lnk'
PROGRAMS = os.path.join(os.environ['APPDATA'], 'Microsoft', 'Windows',
                        'Start Menu', 'Programs')

pyw = os.path.join(os.path.dirname(sys.executable), 'pythonw.exe')
no_console = os.path.exists(pyw)
if not no_console:          # 没有 pythonw 时退回当前解释器，运行时会带一个控制台窗口
    pyw = sys.executable

# 脚本含中文路径，PowerShell 5.1 只认带 BOM 的 UTF-8
ps = """
$ws = New-Object -ComObject WScript.Shell
$lnk = $ws.CreateShortcut((Join-Path $env:LNK_DIR $env:LNK_NAME))
$lnk.TargetPath = $env:PYW
$lnk.Arguments = '"' + $env:MAIN + '"'
$lnk.WorkingDirectory = $env:BASE
$lnk.IconLocation = $env:ICO + ',0'
$lnk.Description = '文献批量下载（IEEE / 知网）'
$lnk.Save()
"""

env = dict(os.environ, LNK_DIR=PROGRAMS, LNK_NAME=LNK_NAME, PYW=pyw,
           MAIN=MAIN, BASE=BASE, ICO=ICO)
r = subprocess.run(['powershell', '-NoProfile', '-ExecutionPolicy', 'Bypass', '-Command', ps],
                   capture_output=True, env=env)
lnk = os.path.join(PROGRAMS, LNK_NAME)
if r.returncode == 0 and os.path.exists(lnk):
    print('快捷方式已更新 ->', lnk)
    print('  目标 :', pyw, '' if no_console else '(未找到 pythonw.exe，运行时会带控制台窗口)')
    print('  脚本 :', MAIN)
    print('  图标 :', ICO, ',0 (256x256)')
else:
    print('创建失败:', r.stderr.decode('utf-8', errors='replace')[:300])

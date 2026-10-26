# -*- coding: utf-8 -*-
# @Time    : 2021/10/13 12:16 
# @Author  : Yong Cao
# @Email   : yongcao_epic@hust.edu.cn
import os
import re
import requests
import time


def _init():
    # 初始化一个全局的字典
    global _global_dict
    _global_dict = {}


def set_value(key, value):
    _global_dict[key] = value


def get_value(key):
    try:
        return _global_dict[key]
    except KeyError as e:
        print(e)


_ARNUM_CACHE = {}
DOI_HEADERS = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/126.0'}


def resolve_doi_url(doi):
    """DOI -> 重定向 -> arnumber -> stampPDF 下载 URL（带缓存）"""
    doi = doi.strip()
    if doi in _ARNUM_CACHE:
        return _ARNUM_CACHE[doi]
    for attempt in range(3):
        if attempt > 0:
            time.sleep(2)
        try:
            r = requests.get('https://doi.org/' + doi, headers=DOI_HEADERS,
                             allow_redirects=True, timeout=30,
                             proxies={'http': None, 'https': None})  # 强制直连
            m = re.search(r'/document/(\d+)', r.url)
            if m:
                url = 'https://ieeexplore.ieee.org/stampPDF/getPDF.jsp?tp=&arnumber=' + m.group(1) + '&ref='
                _ARNUM_CACHE[doi] = url
                return url
            print('   DOI第%d次未解析出arnumber: %s -> %s' % (attempt + 1, doi, r.url[:80]))
        except Exception as e:
            print('   DOI第%d次请求异常: %s %s' % (attempt + 1, type(e).__name__, str(e)[:80]))
    _ARNUM_CACHE[doi] = None
    return None


def downLoad_paper(paper_info, callback=None):
    print("\n" * 2)
    print("执行开始".center(len(paper_info) + 28, '-'))
    succeed = True
    paper_downloaded = 0
    already_exist = 0
    start = time.perf_counter()
    for i, item in enumerate(paper_info.keys()):
        set_value("progress_bar_num", i)
        papername = paper_info[item]['name']
        paperurl = paper_info[item]['url']
        # 文件存储（校验内容：假 PDF/拦截页删除重下）
        if os.path.exists(papername):
            try:
                with open(papername, 'rb') as fh:
                    head = fh.read(4)
            except OSError:
                head = b''
            if head == b'%PDF':
                already_exist += 1
                if callback:
                    callback(i, len(paper_info), 'exist', papername)
                continue
            os.remove(papername)  # 拦截页等假文件：删除重下
        # DOI 条目：无 url 时自动解析 arnumber（带缓存）
        if not paperurl and paper_info[item].get('doi'):
            paperurl = resolve_doi_url(paper_info[item].get('doi', ''))
            if not paperurl:
                succeed = False
                if callback:
                    callback(i, len(paper_info), 'fail', papername, 'DOI解析失败: ' + str(paper_info[item].get('doi', '')))
                continue
        # 下载 + %PDF 校验 + 自动重试（最多 3 次）
        ok_flag = False
        last_err = ''
        for attempt in range(3):
            if attempt > 0:
                time.sleep(3)  # 重试前等待
            try:
                r = requests.get(paperurl, headers=DOI_HEADERS, timeout=60,
                                 proxies={'http': None, 'https': None})  # 强制直连,不走代理
                content = r.content
                if content[:4] != b'%PDF':
                    last_err = '非PDF拦截页(%.0fKB)' % (len(content) / 1024)
                    print('   第%d次 非PDF页 %dB' % (attempt + 1, len(content)))
                    continue
                with open(papername, 'wb') as f:
                    f.write(content)
                ok_flag = True
                paper_downloaded += 1
                if callback:
                    callback(i, len(paper_info), 'ok', papername)
                break
            except Exception as e:
                print(e)
                last_err = str(e)[:60]
        if not ok_flag:
            print("unknown name! parser error", papername)
            succeed = False
            if callback:
                callback(i, len(paper_info), 'fail', papername, last_err or '下载失败')
        # 停一下防禁ip（放慢节奏，降风控）
        time.sleep(3)
        a = '*' * i
        b = '.' * (len(paper_info) - i)
        c = (i / len(paper_info)) * 100
        t = time.perf_counter() - start
        print("\r任务进度:{:>3.0f}% [{}->{}]消耗时间:{:.2f}s".format(c, a, b, t), end="")
    set_value("progress_bar_num", len(paper_info))
    print("\n"+"执行结束".center(len(paper_info)+28,'-'))
    print("-"*50)
    print("Downloaded {} papers and {} paper already exists.".format(paper_downloaded, already_exist))
    print("-" * 50)
    return succeed, paper_downloaded, already_exist
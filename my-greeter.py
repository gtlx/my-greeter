#!/usr/bin/env python3
"""my-greeter - greetd greeter"""
import os, sys, json, struct, socket, tomllib, shutil, termios, tty, select
from pathlib import Path
import configparser
try: from getpass import getpass
except: getpass = None

# ─── config ───
CONF = [Path("/etc/my-greeter/config.toml"), Path.home()/".config"/"my-greeter"/"config.toml",
        Path(__file__).parent/"config.toml"]
DEF = {"log":{"enable":False,"path":"/tmp/my-greeter.log"},"auth":{"default_user":"","auto_login":False},
       "branding":{"title":"Welcome"}}
def load():
    for p in CONF:
        if p.exists():
            with open(p,"rb") as f: return tomllib.load(f)
    return DEF

# ─── log ───
_lh=None; _le=False
def init(c):
    global _lh,_le
    l=c.get("log",{}); _le=l.get("enable",False)
    if not _le: return
    p=Path(l.get("path","/tmp/my-greeter.log"))
    try: p.parent.mkdir(parents=True,exist_ok=True); _lh=open(p,"a",encoding="utf-8"); _le=True
    except: _le=False
def log(lv,m):
    if not _le or _lh is None: return
    from datetime import datetime
    _lh.write(f"[{datetime.now():%Y-%m-%d %H:%M:%S}] [{lv}] {m}\n"); _lh.flush()

# ─── ansi ───
R="\033[0m"
C={"black":30,"red":31,"green":32,"yellow":33,"blue":34,"magenta":35,"cyan":36,"white":37,
   "bright_black":90,"bright_red":91,"bright_green":92,"bright_yellow":93,
   "bright_blue":94,"bright_magenta":95,"bright_cyan":96,"bright_white":97}
A={"bold":1,"dim":2,"italic":3,"underline":4}
def _s(s):
    if not s or not s.strip(): return ""
    c=[]
    for p in s.strip().lower().split():
        if p in C: c.append(str(C[p]))
        elif p in A: c.append(str(A[p]))
    return "\033["+";".join(c)+"m" if c else ""
def st(t,s):
    a=_s(s); return a+t+R if a else t

# ─── scan ───
XD=[Path("/usr/share/wayland-sessions"),Path("/usr/share/xsessions")]
def sess():
    r=[]
    for d in XD:
        if not d.is_dir(): continue
        t=d.name.replace("-sessions","")
        for f in sorted(d.glob("*.desktop")):
            try:
                p=configparser.ConfigParser(); p.read(f); e=p["Desktop Entry"]
                n=e.get("Name",f.stem); c=e.get("Exec","")
                if c: r.append({"name":n,"exec":c,"type":t})
            except: pass
    return r
XU={"nobody","nobody","nfsnobody","guest"}
def users():
    r=[]
    try:
        for l in Path("/etc/passwd").read_text().splitlines():
            p=l.split(":");
            if len(p)<7: continue
            n,_,us,_,_,_,sh=p
            try: u=int(us)
            except: continue
            if u<1000 or n in XU: continue
            if sh in ("/usr/bin/nologin","/bin/false","/sbin/nologin"): continue
            r.append(n)
    except: pass
    return sorted(r)

# ─── plugins ───
PD=[Path.home()/".config"/"my-greeter"/"plugins",Path(__file__).parent/"plugins"]
def plugs():
    from subprocess import run, TimeoutExpired, CalledProcessError
    r=[]; seen=set()
    for d in PD:
        if not d.is_dir(): continue
        for f in sorted(d.iterdir()):
            if f.name.startswith(".") or not os.access(f,os.X_OK): continue
            if f.name in seen: continue
            seen.add(f.name)
            try:
                o=run([f],capture_output=True,timeout=2,text=True)
                for l in o.stdout.strip().split("\n"):
                    l=l.strip()
                    if not l: continue
                    d=json.loads(l)
                    if "lines" in d: r.extend(d["lines"])
            except: log("WARN",f"plugin fail: {f.name}")
    return r

# ─── tty tools ───
def clear(): print("\033[2J\033[H",end="")
def mv(r,c=0): print(f"\033[{r};{c}H",end="")

# ─── key ───
def key(t=None):
    fd=sys.stdin.fileno(); old=termios.tcgetattr(fd)
    try:
        tty.setraw(fd)
        def _r(t2=None):
            if t2 is not None:
                r,_,_=select.select([fd],[],[],t2)
                if not r: return None
            return sys.stdin.read(1)
        c=_r(t)
        if c is None: return None
        if c=="\033":
            s1=_r(0.05); s2=_r(0.05) if s1 else None
            if s1 is None: return "ESC"
            if s2 is None: return None
            co=s1+s2
            if co=="[A": return "UP"
            if co=="[B": return "DOWN"
            if co=="[C": return "RIGHT"
            if co=="[D": return "LEFT"
            return None
        if c in ("\r","\n"): return "ENTER"
        if c=="\t": return "TAB"
        if c=="\x03": raise KeyboardInterrupt
        if c in ("\x7f","\b"): return "BACKSPACE"
        return c
    finally: termios.tcsetattr(fd,termios.TCSADRAIN,old)

# ─── greetd ───
class G:
    def __init__(self):
        sp=os.environ.get("GREETD_SOCK")
        if not sp: log("ERROR","GREETD_SOCK not set"); print("GREETD_SOCK not set",file=sys.stderr); sys.exit(1)
        self.s=socket.socket(socket.AF_UNIX,socket.SOCK_STREAM); self.s.connect(sp)
    def _s(self,o):
        p=json.dumps(o).encode(); self.s.sendall(struct.pack("I",len(p))+p)
    def _r(self):
        d=self.s.recv(4)
        if not d: return {"type":"error","description":"closed"}
        l=struct.unpack("I",d)[0]; b=b""
        while len(b)<l:
            c=self.s.recv(l-len(b))
            if not c: break
            b+=c
        return json.loads(b.decode())
    def cre(self,u): self._s({"type":"create_session","username":u}); return self._r()
    def auth(self,r=None):
        m={"type":"post_auth_message_response"}
        if r is not None: m["response"]=r
        self._s(m); return self._r()
    def start(self,cmd,env=None):
        self._s({"type":"start_session","cmd":cmd,"env":env or []}); return self._r()
    def close(self): self.s.close()

# ─── UI ───
TH={"title":"cyan bold","plugin":"green","env":"dark gray","env_on":"white bold","bdr":"white","bdr_on":"orange","err":"red bold","hint":"dark gray"}

def ui(cfg):
    cols,rows=shutil.get_terminal_size()
    a=cfg.get("auth",{}); b=cfg.get("branding",{})
    pl=plugs(); ss=sess()

    # 可用 session 列表：桌面 + shell
    all_s = ss[:]  # 桌面
    all_s.append({"name":"sh","exec":"/bin/sh","type":"tty"})  # shell

    si=0; du=a.get("default_user","")
    un=du; pw=""; f=2 if du else 1; em=""; fw=min(48,cols-4)

    # 计算垂直居中
    h=13+len(pl)
    tp=max(0,(rows-h)//2)

    def build():
        """构建整屏字符串（一次性输出，消除闪烁）"""
        out=""
        out+=st(f"  {b.get('title','Welcome')}",TH["title"])+"\n"
        if pl:
            for l in pl: out+=st(f"  {l}",TH["plugin"])+"\n"
        out+="\n"
        s=all_s[si]
        out+=st(f"  < {s['name']} >",TH["env_on"] if f==0 else TH["env"])+"\n"
        out+="\n"
        # user
        on=f==1; bc=TH["bdr_on"] if on else TH["bdr"]
        d=un+("\u258c" if on else " ")
        pd=fw-3-len(un)-(1 if on else 0)
        bm=f"\u2502 {d}{' '*max(0,pd)}\u2502"
        out+=st("\u250c\u2500 Login "+"\u2500"*(fw-10)+"\u2510",bc)+"\n"
        out+=(bm if not on else st(bm,TH["bdr_on"]))+"\n"
        out+=st("\u2514"+"\u2500"*(fw-2)+"\u2518",bc)+"\n"
        out+="\n"
        # password
        on2=f==2; bc2=TH["bdr_on"] if on2 else TH["bdr"]
        sts="*"*len(pw)
        d2=sts+("\u258c" if on2 else " ")
        pd2=fw-3-len(sts)-(1 if on2 else 0)
        bm2=f"\u2502 {d2}{' '*max(0,pd2)}\u2502"
        out+=st("\u250c\u2500 Password "+"\u2500"*(fw-14)+"\u2510",bc2)+"\n"
        out+=(bm2 if not on2 else st(bm2,TH["bdr_on"]))+"\n"
        out+=st("\u2514"+"\u2500"*(fw-2)+"\u2518",bc2)+"\n"
        if em: out+="\n"+st(f"  {em}",TH["err"])+"\n"
        out+="\n"+st("  Tab:Focus  \u2190\u2192:Session  Enter:Next",TH["hint"])+"\n"
        return out

    def render():
        """全屏刷新"""
        nonlocal em
        sys.stdout.write("\033[2J\033[H"+"\n"*tp+build())
        sys.stdout.flush()

    # 初始渲染
    render()

    # ── loop ──
    while True:
        k=key()
        if k=="TAB": f=(f+1)%3; em=""; render()
        elif k in ("RIGHT","DOWN"):
            if f==0: si=(si+1)%len(all_s); render()
        elif k in ("LEFT","UP"):
            if f==0: si=(si-1)%len(all_s); render()
        elif k=="ENTER":
            if f==1 and un: f=2; render()
            elif f==2 and pw: break
        elif k=="BACKSPACE":
            if f==1 and un: un=un[:-1]; render()
            elif f==2 and pw: pw=pw[:-1]; render()
        elif k=="ESC":
            if f!=0: f=0; render()
        elif k=="q": return
        elif k and len(k)==1 and k.isprintable():
            if f==1: un+=k; render()
            elif f==2: pw+=k; render()

    if not un or not pw: log("WARN","empty"); return
    log("INFO",f"login: {un}")

    if "--preview" in sys.argv:
        clear(); print(st("  [Preview] OK",TH["title"]))
        print(st(f"  Session: {all_s[si]['name']}",TH["plugin"]))
        print(st(f"  User: {un}",TH["plugin"])); return

    # ── auth ──
    c=G(); r=c.cre(un)
    while r["type"]!="success":
        if r["type"]=="auth_message":
            mt=r.get("auth_message_type","visible"); t=r.get("auth_message","")
            if mt=="secret": r=c.auth(pw)
            elif mt in ("info","error"): em=f"[{mt}] {t}"; render(); r=c.auth()
            else: r=c.auth(input())
        elif r["type"]=="error":
            em=r.get("description","auth error"); log("WARN",em); render(); pw=""; f=2
            while True:
                k2=key()
                if k2=="ENTER" and pw: break
                elif k2=="BACKSPACE" and pw: pw=pw[:-1]; render()
                elif k2 and len(k2)==1 and k2.isprintable(): pw+=k2; render()
                elif k2=="TAB": f=(f+1)%3; render()
                elif k2=="q": c.close(); return
            r=c.auth(pw)

    log("INFO","auth ok")
    sel=all_s[si]
    clear(); print(st(f"  Starting {sel['name']}...",TH["title"]))
    r=c.start([sel["exec"]])
    if r["type"]=="success": log("INFO","done"); c.close(); os._exit(0)
    else: em=f"Start fail: {r.get('description','?')}"; render(); c.close()

# ─── main ───
def main():
    c=load(); init(c); log("INFO","start")
    try: ui(c)
    except KeyboardInterrupt: print()
    except Exception as e: log("ERROR",str(e)); print(f"\n  Error: {e}",file=sys.stderr); sys.exit(1)
if __name__=="__main__": main()

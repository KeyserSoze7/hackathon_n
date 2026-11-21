"""Build the 2:00 demo video from captured frames. Output: assets/video/marg_demo.mp4"""
import pathlib, subprocess
from PIL import Image, ImageDraw, ImageFont

ROOT = pathlib.Path(__file__).resolve().parents[2]
V = ROOT / 'assets' / 'video'; F = V / 'frames'; S = V / 'scenes'; S.mkdir(exist_ok=True)
FF = r"C:\Python312\Lib\site-packages\imageio_ffmpeg\binaries\ffmpeg-win-x86_64-v9.0.2.exe"
ANIM = ROOT / 'assets' / 'load_animation.mp4'
W, H, BG, INK, MUTED, YEL = 1280, 720, (242, 241, 234), (17, 19, 23), (75, 85, 99), (245, 183, 0)
B = lambda s: ImageFont.truetype(r'C:\Windows\Fonts\segoeuib.ttf', s)
R = lambda s: ImageFont.truetype(r'C:\Windows\Fonts\segoeui.ttf', s)

def wrap(d, text, font, width):
    lines, cur = [], ''
    for w in text.split():
        t = (cur + ' ' + w).strip()
        if d.textlength(t, font=font) <= width: cur = t
        else: lines.append(cur); cur = w
    return lines + [cur]

def text_block(d, x, y, head, sub, width, hs=40, ss=26):
    for l in wrap(d, head, B(hs), width): d.text((x, y), l, font=B(hs), fill=INK); y += int(hs * 1.25)
    y += 10
    for l in wrap(d, sub, R(ss), width): d.text((x, y), l, font=R(ss), fill=MUTED); y += int(ss * 1.4)
    return y

def kerb(d, y, h=8):
    for x in range(0, W, 24): d.rectangle([x, y, x + 11, y + h - 1], fill=INK); d.rectangle([x + 12, y, x + 23, y + h - 1], fill=YEL)

def card(head, sub):
    im = Image.new('RGB', (W, H), BG); d = ImageDraw.Draw(im); kerb(d, 0)
    text_block(d, 140, 220, head, sub, 1000, 54, 30); return im

def phone(name, head, sub):
    im = Image.new('RGB', (W, H), BG); d = ImageDraw.Draw(im); kerb(d, 0)
    shot = Image.open(F / f'{name}.png').convert('RGB'); h = 640; w = int(shot.width * h / shot.height); shot = shot.resize((w, h), Image.LANCZOS)
    x0, y0 = 150, 44
    d.rounded_rectangle([x0 - 10, y0 - 10, x0 + w + 10, y0 + h + 10], radius=34, fill=INK)
    mask = Image.new('L', (w, h), 0); ImageDraw.Draw(mask).rounded_rectangle([0, 0, w, h], radius=24, fill=255); im.paste(shot, (x0, y0), mask)
    text_block(d, x0 + w + 90, 240, head, sub, W - (x0 + w + 90) - 90); return im

def desk(name, head, sub):
    im = Image.new('RGB', (W, H), BG); d = ImageDraw.Draw(im); kerb(d, 0)
    shot = Image.open(F / f'{name}.png').convert('RGB'); w = 920; h = int(shot.height * w / shot.width); shot = shot.resize((w, h), Image.LANCZOS)
    x0, y0 = (W - w) // 2, 26
    d.rounded_rectangle([x0 - 4, y0 - 4, x0 + w + 4, y0 + h + 4], radius=14, fill=INK); im.paste(shot, (x0, y0))
    y = y0 + h + 18
    for l in wrap(d, head, B(30), 1120)[:1]: d.text((80, y), l, font=B(30), fill=INK)
    for i, l in enumerate(wrap(d, sub, R(21), 1120)[:2]): d.text((80, y + 42 + i * 28), l, font=R(21), fill=MUTED)
    return im

def closing():
    subprocess.run([r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe", '--headless', '--disable-gpu', '--hide-scrollbars', '--force-device-scale-factor=1',
                    '--window-size=430,512', f'--screenshot={V / "logo.png"}', (ROOT / 'assets' / 'marg-logo.svg').as_uri()], capture_output=True)
    im = Image.new('RGB', (W, H), BG); d = ImageDraw.Draw(im); kerb(d, 0)
    logo = Image.open(V / 'logo.png').convert('RGB').crop((0, 12, 430, 420)).resize((344, 326), Image.LANCZOS)
    im.paste(logo, (130, 197))
    text_block(d, 560, 210, 'Where did the money go? Did the fix last? Where should the next rupee go?', 'MARG answers all three, from a citizen’s complaint to the contractor’s bill to the next rupee.', 620, 40, 26)
    return im

SCENES = [  # (kind, frame, headline, subline, seconds); the intro animation adds 6 s first. Total must be 120 s.
    ('card', None, 'Every monsoon, Mumbai spends crores fixing the same roads.', 'Nobody can easily say where the money went, whether the fix lasted, or where the next rupee should go.', 6),
    ('card', None, 'MARG: one tool for the whole money trail.', 'Ward money trail · Repair auditor · Contractor scorecard · Next-rupee planner · Complaint-to-work-order linker · Citizen accountability bot.', 8),
    ('phone', 'p_answer', 'Ask in your own words.', 'A citizen asks in Hinglish where the money went. Claude answers in plain language from the records: warranty status, the last repair, what was billed, what is flagged.', 9),
    ('phone', 'p_report_what', 'Broken again? Report it in four steps.', 'What is wrong, a photo, where it is, then send.', 6),
    ('phone', 'p_review', 'Check it, then send.', 'The landmark and location travel with the report, so it reaches the right contract.', 4),
    ('phone', 'p_tracker', 'Matched to the contract, then tracked.', 'On a warranty road the bill is flagged and the original contractor, not the public, owes the repair.', 7),
    ('phone', 'p_me', 'My reports: every report, its status, its impact.', 'No login needed to report. Sign in with email and password to keep your reports on any device.', 7),
    ('desk', 'd_receipt', 'Kurla Andheri Road: ₹30.5L billed across 35 repair jobs.', 'Every road has a receipt: every rupee on one stretch, with its warranty status up front.', 7),
    ('desk', 'd_trail', 'Complaint to repair to failure, connected.', 'The proof trail links citizen complaints to the work orders that answered them, and to the fixes that failed within 30 days.', 5),
    ('desk', 'd_notice', 'One click: a defect notice drafted by Claude.', 'In English or Marathi, citing the exact work orders. Code computes every number; Claude only writes.', 8),
    ('desk', 'd_city', '₹13.43 Cr spent. ₹60.3L billed on roads still under warranty.', '527 bills need explanation: warranty bills, rate-card overruns, overlapping work orders, rain-day work and repeat bills.', 8),
    ('desk', 'd_flagged', 'The repair auditor, bill by bill.', 'Ranked by rupees at stake. Each flag says "needs explanation", never "fraud", and the contractor can reply on the record.', 5),
    ('desk', 'd_contractors', 'Contractors are judged fairly.', 'Each failure rate sits beside what the rain, tides and roads predict. No grades and no blame without context.', 8),
    ('desk', 'd_nextrupee', 'The next rupee goes where it does the most good.', 'Warranty roads cost the city ₹0, so the budget moves to the roads where it avoids the most harm.', 8),
    ('phone', 'p_admin_report', 'The ward office moves each report forward.', 'Officers review, hold payment, notify the contractor and mark it fixed. The citizen sees every step.', 7),
    ('phone', 'p_admin_flags', 'And answers every flag on the record.', 'Bills with no reply yet, one tap from a public right of reply.', 5),
    ('close', None, '', '', 6),
]
assert 6 + sum(s[4] for s in SCENES) == 120

parts = []
intro = S / '00_intro.mp4'
subprocess.run([FF, '-v', 'error', '-y', '-i', str(ANIM), '-t', '6', '-an', '-vf', 'fps=30,format=yuv420p,fade=t=out:st=5.6:d=0.4:color=0xF2F1EA',
                '-c:v', 'libx264', '-crf', '18', '-preset', 'fast', str(intro)], check=True)
parts.append(intro)
for i, (kind, name, head, sub, sec) in enumerate(SCENES, 1):
    im = card(head, sub) if kind == 'card' else phone(name, head, sub) if kind == 'phone' else desk(name, head, sub) if kind == 'desk' else closing()
    png = S / f'{i:02d}.png'; im.save(png)
    mp4 = S / f'{i:02d}.mp4'
    vf = f'fps=30,format=yuv420p,zoompan=z=\'min(zoom+0.0004,1.03)\':d={sec * 30}:s={W}x{H}:fps=30,fade=t=in:st=0:d=0.4:color=0xF2F1EA,fade=t=out:st={sec - 0.4}:d=0.4:color=0xF2F1EA,format=yuv420p'
    subprocess.run([FF, '-v', 'error', '-y', '-loop', '1', '-i', str(png), '-t', str(sec), '-vf', vf, '-c:v', 'libx264', '-crf', '18', '-preset', 'fast', str(mp4)], check=True)
    parts.append(mp4); print('scene', i, sec, 's')

lst = S / 'list.txt'; lst.write_text(''.join(f"file '{p.as_posix()}'\n" for p in parts))
silent = S / 'video.mp4'
subprocess.run([FF, '-v', 'error', '-y', '-f', 'concat', '-safe', '0', '-i', str(lst), '-c:v', 'libx264', '-pix_fmt', 'yuv420p', '-crf', '18', '-preset', 'fast', '-r', '30', str(silent)], check=True)
out = V / 'marg_demo.mp4'
# Music: the brand animation's own track, looped quietly under the whole video, faded in and out.
subprocess.run([FF, '-v', 'error', '-y', '-i', str(silent), '-stream_loop', '-1', '-i', str(ANIM), '-map', '0:v', '-map', '1:a',
                '-af', 'volume=0.55,afade=t=in:st=0:d=1,afade=t=out:st=116:d=4', '-t', '120', '-c:v', 'copy', '-c:a', 'aac', '-b:a', '160k', '-shortest', str(out)], check=True)
print('done', out)

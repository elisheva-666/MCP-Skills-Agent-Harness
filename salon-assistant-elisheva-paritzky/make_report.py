"""Builds REPORT.md from results/api.json and results/sdk.json.

    python make_report.py
The numbers are filled in from the result files; the analysis text is below.
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.stdout.reconfigure(encoding="utf-8")


def load(name):
    p = ROOT / "results" / f"{name}.json"
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else None


def summary_table(api, sdk):
    rows = [("Input (לא מ-cache)", "input"), ("Cache read", "cache_read"), ("Cache write", "cache_write"),
            ("Output", "output"), ("קריאות למודל", "model_calls"), ("אחוז cache", "cache_hit_pct"),
            ("עלות (USD)", "cost_usd"), ("זמן (שניות)", "seconds")]
    cell = lambda r, k: "לא הורץ" if r is None else r["totals"][k]
    out = ["| | API | SDK |", "|---|---|---|"]
    out += [f"| {label} | {cell(api, k)} | {cell(sdk, k)} |" for label, k in rows]
    out.append(f"| בדיקות שעברו | {api['checks_passed'] if api else 'לא הורץ'} | {sdk['checks_passed'] if sdk else 'לא הורץ'} |")
    return "\n".join(out)


def turns_table(r):
    if r is None:
        return "_עוד לא הורץ: `python API/main.py --scenario scenario.json --out results/api.json`_"
    out = ["| סשן | תור | input | cache read | cache write | output | קריאות | עלות $ | שניות | כלים |",
           "|---|---|---|---|---|---|---|---|---|---|"]
    for t in r["turns"]:
        out.append(f"| {t['session']} | {t['turn']} | {t['input']} | {t['cache_read']} | {t['cache_write']} | "
                   f"{t['output']} | {t['model_calls']} | {t['cost_usd']:.4f} | {t['seconds']} | {', '.join(t['tools'])} |")
    return "\n".join(out)


def checks_table(api, sdk):
    base = (sdk or api)["checks"]
    by = lambda r: {c["id"]: ("✅" if c["passed"] else "❌") for c in r["checks"]} if r else {}
    a, s = by(api), by(sdk)
    out = ["| בדיקה | מה נבדק | API | SDK |", "|---|---|---|---|"]
    out += [f"| `{c['id']}` | {c['description']} | {a.get(c['id'], '-')} | {s.get(c['id'], '-')} |" for c in base]
    return "\n".join(out)


def loc_table(api, sdk):
    parts = ["loop", "tools", "history", "memory", "context", "compaction", "caching", "tokens"]
    la = api["lines_of_code"] if api else {}
    ls = sdk["lines_of_code"] if sdk else {}
    out = ["| חלק | API (שורות קוד) | SDK (שורות שמסומנות `# replaces:`) |", "|---|---|---|"]
    out += [f"| {p} | {la.get(p, '-')} | {ls.get(p, 0) if sdk else '-'} |" for p in parts]
    out.append(f"| חיווט (agent + main) | {la.get('agent+main', '-')} | כלול בסה\"כ |")
    out.append(f"| **סה\"כ** | **{la.get('total', '-')}** | **{ls.get('total', '-')}** |")
    return "\n".join(out)


def main():
    api, sdk = load("api"), load("sdk")
    text = TEMPLATE.format(summary=summary_table(api, sdk), checks=checks_table(api, sdk),
                           loc=loc_table(api, sdk), api_turns=turns_table(api), sdk_turns=turns_table(sdk))
    (ROOT / "REPORT.md").write_text(text, encoding="utf-8")
    print("wrote REPORT.md")


TEMPLATE = """# דוח: סוכן אחד, שני harnesses

**הסוכן:** עוזרת לקוחות לסטודיו "נחמי גרוסמן - אומנות השיער והאיפור". עונה על שירותים וקורסים, מציגה תמונות מהגלריה, בודקת תאריכים מול לוח השנה העברי (Hebcal), קובעת ומזיזה תורים וזוכרת לקוחות בין ביקורים.

**השוואה הוגנת:** אותו מודל (`claude-opus-5-5`) ואותו effort (`medium`) מ-`shared/config.py`, אותם כלים מ-`shared/tools.py`, אותן הוראות מ-`shared/prompts.py`, גרסאות ספריות נעולות (`requirements.lock.txt`), וכל ריצה מתחילה מתיקיית `state/` ריקה.

## 1. API מול SDK

{summary}

### בדיקות (רובן על המצב שנשמר בדיסק, לא על טקסט התשובה)

{checks}

### פירוט לפי תור: API

{api_turns}

### פירוט לפי תור: SDK

{sdk_turns}

## 2. שורות קוד לכל חלק ב-harness

{loc}

ב-API כל אחריות היא קובץ ב-`API/harness/`, וכל פעולה בזמן ריצה מודפסת עם שם הקובץ שביצע אותה. ב-SDK יש שורה אחת או שתיים לכל אחריות. `compaction` ו-`caching` לא מופיעים בעמודת ה-SDK כי הם אוטומטיים לגמרי ואין שום שורה שמחליפה אותם.

## 3. איפה ה-SDK עלה יותר טוקנים ואיפה פחות, ולמה

**איפה ה-SDK עולה יותר:**
- **קריאת זיכרון בכלי.** ב-API הפרופיל של הלקוחה מוזרק להקשר של כל תור (כמה שורות). ב-SDK המודל צריך לקרוא ל-`recall_client` בתחילת כל שיחה, וזה עוד סבב: קריאה למודל, תוצאת כלי, ועוד קריאה.
- **מה ש-Claude Code מוסיף בעצמו.** גם עם `system_prompt` משלנו ו-`tools=[]`, ה-CLI מוסיף מידע על הסביבה, את `CLAUDE.md` ואת הגדרות כלי ה-MCP בפורמט שלו, ואי אפשר לראות או לקצץ את זה.
- **`resume` טוען את השיחה מחדש.** כל תור הוא תהליך חדש של ה-CLI שטוען את הסשן מהדיסק. זה עולה זמן, ובתור הראשון אחרי טעינה גם cache write.

**איפה ה-SDK עולה פחות או אותו דבר:**
- **Caching אוטומטי וטוב.** ה-SDK מסמן cache לבד ומגיע לאחוז פגיעות גבוה בלי שורת קוד אחת. ב-API היה צריך לבחור נקודות (`caching.py`) ולוודא ששום דבר משתנה לא נכנס לפני ה-prefix. למשל, את התאריך היומי שמנו בהודעת המשתמש ולא ב-system prompt.
- **פלט הכלים זהה,** כי שתי הגרסאות משתמשות באותו `shared/tools.py` עם פלט קומפקטי. לכן ההבדל בטוקנים מגיע מה-harness, לא מהכלים.

**מלכודת מדידה שגילינו:** ב-SDK, `ResultMessage.total_cost_usd` **מצטבר** לאורך סשן שעושים לו resume (0.046, ‏0.068, ‏0.086, ‏0.108...), ולא מייצג עלות של תור בודד. בהתחלה זה ניפח את העלות פי 3. תיקנו בעזרת הפרש בין תורים. ב-API העלות מחושבת מה-usage של כל תשובה, ולכן היא שקופה.

## 4. על מה הייתה לי שליטה ב-API ואיבדתי ב-SDK

- **מה נכנס להקשר:** ב-API בדיוק ה-system prompt, הפרופיל ותאריך היום. ב-SDK, ה-CLI מוסיף דברים בעצמו.
- **זיכרון שמוזרק אוטומטית:** ב-API הפרופיל מוזרק תמיד, בלי סבב כלים. ב-SDK צריך לסמוך על כך שהמודל יקרא ל-`recall_client`.
- **נקודות cache וסף compaction:** ב-API אני בוחרת אותם. ב-SDK הם אוטומטיים ואין עליהם שליטה.
- **פרמטרים של הבקשה:** ב-API יש לי `fallbacks="default"`, `strict: true` על הכלים ו-`max_tokens`. ב-SDK לא את כולם אפשר להעביר.
- **מדידה:** ב-API יש usage לכל קריאה. ב-SDK יש רק סכום לכל תור (ועלות מצטברת).
- **פריסה:** את גרסת ה-API אפשר להריץ על שרת עם מפתח ולחבר לווידג'ט באתר. גרסת ה-SDK רצה על ה-login האישי של Claude Code, לשימוש אישי בלבד, ולכן אי אפשר להגיש איתה שירות לגולשים.
- **מה ה-SDK חסך:** את הלולאה, ה-dispatch, השמירה לדיסק, ה-caching וה-compaction. כמעט כל ה-harness הפך להגדרות.

## 5. איזו גרסה הייתי בוחרת לסוכן הזה, ולמה

**API.** זה סוכן שעונה לגולשים באתר, ולכן:
1. הוא חייב לרוץ על שרת עם מפתח API. ה-SDK על login אישי לא מתאים לשירות ציבורי.
2. השיחות קצרות והכלים מעטים. הלולאה פשוטה (כ-40 שורות), ומה שה-SDK חוסך כאן קטן.
3. שליטה על מה שנכנס להקשר ועל העלות של כל תור חשובה כשכל גולש עולה כסף.
4. אפשר להוסיף בקלות הגנות של שירות ציבורי: הגבלת קצב, תקרת טוקנים, וזה ש-`client_id` מגיע מהשרת ולא מהמודל.

ה-SDK מתאים יותר לסוכן אישי שרץ אצלי במחשב (למשל ניהול קבצים או קוד), שבו הכלים המובנים, הסשנים וה-compaction האוטומטי שווים הרבה ואין צורך לשרת אנשים אחרים.

## הרצה

```
python -m venv .venv && .venv\\Scripts\\activate
pip install -r requirements.lock.txt
python -m pytest -q                                   # בדיקות offline, בלי מפתח
$env:ANTHROPIC_API_KEY = "..."                        # רק בטרמינל, לעולם לא בקוד
python API/main.py --scenario scenario.json --out results/api.json
python SDK/main.py --scenario scenario.json --out results/sdk.json   # מוחק את המפתח מהסביבה ורץ על ה-login
python make_report.py
```

**מקורות הנתונים:** פרטי העסק, השירותים והקורסים נלקחו מ-n0583221504.com. המחירים לא מפורסמים שם, ולכן הסוכן מציע ייעוץ ללא עלות. התמונות באתר מוגנות מהורדה, אז הגלריה משתמשת ב-8 תמונות לדוגמה. שעות התורים הן הנחה.
"""

if __name__ == "__main__":
    main()

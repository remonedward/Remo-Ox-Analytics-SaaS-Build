# REMO_OX Analytics — تحليلات الأعمال الذكية

> **Production-Ready, Arabic-First & English Business Analytics SaaS for Small & Medium Businesses**  
> **منصة تحليلات الأعمال السحابية الاحترافية للشركات الصغيرة والمتوسطة باللغتين العربية والإنجليزية**

[![Python 3.11+](https://img.shields.io/badge/python-3.11%20%7C%203.12%20%7C%203.13-blue.svg)](https://www.python.org/)
[![Tests](https://img.shields.io/badge/tests-101%20passing-brightgreen.svg)]()
[![Coverage](https://img.shields.io/badge/coverage-84%25-success.svg)]()
[![Code Style: Ruff](https://img.shields.io/badge/code%20style-ruff-000000.svg)](https://github.com/astral-sh/ruff)
[![Streamlit Cloud Ready](https://img.shields.io/badge/deploy-Streamlit%20Cloud-FF4B4B.svg)](https://streamlit.io/cloud)

---

## 🌟 نظرة عامة / Project Overview

**REMO_OX Analytics** هو تطبيق SaaS متكامل مبني بلغة بايثون وواجهة Streamlit لمساعدة أصحاب الأعمال والمديرين الماليين في منطقة الشرق الأوسط وشمال أفريقيا (MENA) والعالم على استخراج رؤى دقيقة من ملفات Excel المعقدة والتقارير المالية والمخزون بدون أي تضارب أو أخطاء حسابية.

**REMO_OX Analytics** is an enterprise-grade, privacy-first business analytics platform designed for Streamlit Community Cloud. It allows business owners and finance teams to ingest messy Arabic/English Excel workbooks, automatically detect schemas and business roles, calculate deterministic analytics, export branded Arabic/English PDF reports, and query their data using an AI Assistant powered by Google Gemini (or any LiteLLM-supported LLM).

---

## 🏛️ المعمارية البرمجية / Architecture & Engineering Highlights

### 1. برمجة كائنية التوجه بالكامل (Strict OOP Architecture)
- **الكبسلة والأنماط التصميمية (Encapsulation & Design Patterns)**: تم بناء المشروع بالكامل وفق نمط البرمجة كائنية التوجه (OOP) مع واجهات بروتوكول واضحة (`Protocols`)، ونمط الاستراتيجية (`Strategy Pattern`) لإدارة التخزين، وفصل تام بين طبقة البيانات (`data`)، وطبقة المحرك الحسابي (`analytics`)، وطبقة الخدمات (`services`)، وطبقة العرض والمكونات (`ui/views`, `ui/components`).
- **قابلية التوسع المستقبلي (Future-Proof Extensibility)**: إضافة أي تقارير جديدة، أو مزودات ذكاء اصطناعي، أو قواعد بيانات يتم عبر إضافة فئات فرعية دون المساس بجوهر النظام.

### 2. قواعد بيانات تستوعب ملايين المستخدمين مع النسخ الاحتياطي الكامل (Scalable Database & Backup)
- **بيئة الإنتاج (Production)**: قاعدة بيانات **PostgreSQL على Supabase** مزودة بخاصية عزل أمان مستوى الصفوف (**Row-Level Security - RLS**) لضمان عزل بيانات كل مستخدم وشركة بنسبة 100%.
- **بيئة التطوير المحلي (Local Development)**: محرك **SQLite** عالي الأداء مع وضع الكتابة المسبقة (**WAL Mode**)، وقفل تسلسلي آمن للعمليات المتزامنة (`threading.Lock`)، وتشفير كلمات المرور بواسطة `PBKDF2-HMAC-SHA256`.
- **تحميل النسخة الاحتياطية الكاملة للمشرف (Full Database Backup Download)**: إمكانية تنزيل قاعدة البيانات بالكامل مباشرة بضغطة زر واحدة من واجهة المشرف عبر دالة `export_database_dump()`.

### 3. دعم Google Gemini ومزودي الذكاء الاصطناعي مع تحكم التكلفة (Google Gemini & Multi-Provider LLM)
- **النموذج الافتراضي**: محرك **Google Gemini 2.0 Flash** (`gemini/gemini-2.0-flash`) — يوفر أحدث قدرات الاستدلال الرياضي واللغوي بسرعة فائقة وبأقل تكلفة تشغيلية ممكنة.
- **مرونة تامة (LiteLLM Agnostic)**: إمكانية التبديل الفوري لأي مزود آخر بدون تعديل سطر كود واحد:
  - `gemini/gemini-2.0-flash` (Google)
  - `openai/gpt-4o-mini` (OpenAI)
  - `anthropic/claude-3-5-haiku` (Anthropic)
  - `groq/llama-3.1-70b-versatile` (Groq)
  - `deepseek/deepseek-chat` (DeepSeek)
  - `ollama/llama3.2` (Local Self-Hosted)
- **النموذج الاحتياطي التلقائي (Automatic Fallback)**: تبديل فوري لنموذج احتياطي عند حدوث انقطاع أو تجاوز حد الطلبات.

### 4. حوسبة حتمية بدون أي هلوسة (Zero Hallucination Deterministic Engine)
- **قاعدة ذهبية**: لا يقوم نموذج الذكاء الاصطناعي بأي عمليات حسابية أو جمع أرقام في رأسه مطلقاً.
- يستدعي الذكاء الاصطناعي أدوات حسابية مهيكلة (`Tool Calling`) يتم تنفيذها بواسطة خوارزميات Pandas حتمية نقية.
- الحد الأقصى للنتائج هو 50 سجلاً لتجنب استهلاك الذاكرة وتكلفة الرموز.

### 5. أمان وخصوصية البيانات أولاً (Privacy & Security First)
- **بوابة الموافقة الصريحة**: لا يتم إرسال أي استفسار للذكاء الاصطناعي قبل موافقة المستخدم الصريحة.
- **حماية البيانات الخام**: لا يتم إرسال الصفوف الخام إلى الذكاء الاصطناعي إطلاقاً بشكل افتراضي؛ يتم فقط إرسال الملخصات الإحصائية والأعمدة المعنية بالتحليل.
- **حماية أمنية مشددة**: فحص البايتات السحرية (Magic Bytes `PK\x03\x04`)، حماية ضد قنابل الـ Zip، تعقيم أسماء الملفات، ومحدد لمعدل الطلبات (`RateLimiter`).

### 6. تقارير الأعمال الخمسة الجاهزة (5 Ready-Made Business Reports)
1. **نظرة عامة على المبيعات (Sales Overview)**: إجمالي المبيعات، أفضل وأضعف شهر، متوسط المبيعات الشهرية، ونسبة النمو الشهري (MoM %).
2. **أفضل المنتجات (Top Products & Pareto 80/20)**: ترتيب المنتجات بحسب الإيرادات، تحديد المنتجات المسؤولة عن 80% من المبيعات، وهوامش الربح.
3. **المخزون بطيء الحركة (Slow-Moving Inventory)**: المنتجات التي لم تتحرك لأكثر من 90 يوماً مع تقدير رأس المال المعطل.
4. **تقادم المديونيات (Receivables Aging)**: فترات الاستحقاق (الحالية، 1-30، 31-60، 61-90، 90+ يوم)، وأكبر العملاء المتأخرين في السداد.
5. **تفصيل المصروفات (Expense Breakdown)**: توزيع المصروفات بحسب الفئات، نسبتها المئوية، والاتجاه الشهري للإنفاق.

### 7. التصدير لملفات PDF باللغة العربية (Native Arabic PDF Reports)
- تضمين خط **Amiri** العربي الأصيل (`Amiri-Regular.ttf`, `Amiri-Bold.ttf`).
- إعادة تشكيل الحروف العربية والنصوص ثنائية الاتجاه بواسطة `arabic-reshaper` و`python-bidi`.
- رسوم بيانية توضيحية مدمجة بألوان الهوية البصرية (`#1B4F72`).

---

## 📁 هيكل المشروع / Project Structure

```
REMO_OX Analytics/
├── app.py                      # منسق التطبيق الرئيسي / Application Coordinator
├── requirements.txt            # المكتبات المحددة / Pinned dependencies
├── pyproject.toml              # إعدادات Ruff و Pytest والتغطية
├── .env.example                # نموذج متغيرات البيئة
├── .streamlit/
│   ├── config.toml             # ثيم وألوان التطبيق
│   └── secrets.toml.example    # نموذج أسرار Streamlit Cloud
├── assets/
│   └── fonts/                  # خطوط Amiri العربية الحرة (OFL)
├── core/                       # النواة المشتركة
│   ├── config.py               # إدارة الإعدادات عبر Pydantic v2
│   ├── security.py             # حماية الملفات وتحديد معدل الطلبات
│   ├── i18n.py                 # الترجمة ودعم واجهة RTL/LTR
│   └── logging_setup.py        # تسجيل الأحداث مع إخفاء الأسرار
├── data/                       # استيعاب ومعالجة البيانات
│   ├── ingest.py               # تنظيف وتطبيع الأرقام والتواريخ
│   ├── mapping.py              # المطابقة الضبابية للأدوار الـ 16
│   └── quality.py              # فحص جودة البيانات واكتشاف القيم الشاذة
├── analytics/                  # المحرك الحسابي الحتمي
│   ├── schemas.py              # نماذج البيانات Pydantic
│   ├── filters.py              # عوامل التصفية الآمنة
│   ├── engine.py               # التجميعات وحساب الفترات
│   ├── reports.py              # بناة التقارير الخمسة
│   └── charts.py               # توليد الرسوم البيانية العربية
├── storage/                    # طبقة التخزين وعزل العملاء
│   ├── base.py                 # واجهة التخزين والنسخ الاحتياطي
│   ├── local_backend.py        # محرك SQLite WAL للتطوير المحلي
│   └── supabase_backend.py     # محرك PostgreSQL Supabase للإنتاج
├── services/                   # طبقة خدمات الأعمال
│   ├── auth_service.py         # التوثيق والخطط والنسخ الاحتياطي
│   ├── dataset_service.py      # إدارة الملفات والذاكرة المؤقتة
│   └── export_service.py       # إدارة حصص التصدير وPDF
├── ai/                         # المساعد الذكي
│   ├── provider.py             # موجه LiteLLM المدمج مع Gemini
│   ├── tools.py                # أدوات التول الفنية للذكاء الاصطناعي
│   └── orchestrator.py         # الحوار متعدد الجولات واستهلاك الحصص
├── export/                     # التصدير
│   └── pdf.py                  # توليد تقارير PDF المنسقة
├── ui/                         # واجهة المستخدم والمكونات
│   ├── session.py              # إدارة حالة الجلسة الآمنة
│   ├── theme.py                # أنماط CSS والخطوط
│   ├── navigation.py           # الشريط الجانبي والتبديل بين الصفحات
│   ├── components/             # المكونات القابلة لإعادة الاستخدام
│   └── views/                  # شاشات التطبيق السبع
├── supabase/
│   └── schema.sql              # مخطط PostgreSQL و RLS للإنتاج
├── sample_data/                # بيانات واقعية للتجربة والاختبار
│   ├── sales_ar.xlsx           # مبيعات عربية حقيقية
│   ├── sales_en.xlsx           # مبيعات إنجليزية
│   ├── inventory.xlsx          # مخزون
│   ├── receivables.xlsx        # مديونيات
│   └── expenses.xlsx           # مصروفات
└── tests/                      # 101 اختبار تغطي كافة المسارات
    ├── test_e2e.py             # اختبارات التكامل الشاملة (E2E)
    ├── test_core.py            # اختبارات الإعدادات واللغات
    ├── test_security.py        # اختبارات الحماية وقنابل الملفات
    ├── test_ingest.py          # اختبارات تنظيف البيانات
    ├── test_mapping.py         # اختبارات المطابقة الضبابية
    ├── test_engine.py          # اختبارات المحرك الحسابي
    ├── test_reports.py         # اختبارات التقارير الخمسة
    ├── test_ai.py              # اختبارات المساعد الذكي
    ├── test_pdf.py             # اختبارات تصدير PDF العربي
    └── test_services.py        # اختبارات طبقة الخدمات
```

---

## 🚀 التشغيل والتثبيت المحلي / Local Setup Guide

> **ملاحظة هامة**: يجب دائماً تفعيل بيئة العمل الافتراضية `venv` وعدم تثبيت الحزم مباشرة على نظام التشغيل.

### 1. إعداد البيئة الافتراضية وتثبيت المتطلبات
```powershell
# في نظام ويندوز (Windows PowerShell):
python -m venv venv
.\venv\Scripts\Activate.ps1

# تثبيت المتطلبات المحددة بدقة
pip install -r requirements.txt
```

### 2. إعداد المتغيرات والأسرار (Configuration)
قم بإنشاء ملف `.streamlit/secrets.toml` أو ملف `.env` (استناداً إلى `.env.example`):
```toml
# اختيار نموذج الذكاء الاصطناعي (افتراضياً Google Gemini الحديث ومنخفض التكلفة)
LLM_MODEL = "gemini/gemini-2.0-flash"
LLM_API_KEY = "AIzaSyYourGeminiApiKeyHere"

# بريد المشرف (للتحكم وتنزيل قاعدة البيانات بالكامل)
ADMIN_EMAILS = "admin@example.com"
DEFAULT_PLAN = "trial"

# لتشغيل بيئة الإنتاج على Supabase (اتركها فارغة للتطوير المحلي على SQLite):
SUPABASE_URL = ""
SUPABASE_ANON_KEY = ""
SUPABASE_SERVICE_KEY = ""
```

### 3. توليد ملفات البيانات التجريبية (Sample Data)
```powershell
.\venv\Scripts\python.exe sample_data/generate_samples.py
```

### 4. تشغيل التطبيق (Run Streamlit App)
```powershell
.\venv\Scripts\streamlit.exe run app.py
```
افتح المتصفح على: `http://localhost:8501`

---

## 🧪 الاختبارات وضمان الجودة / Testing & Quality Assurance

المشروع مزود بـ **101 اختبار آلي** تغطي كافة المسارات الحسابية والأمنية وتكامل النظام بنسبة تغطية تتجاوز 84%:

### تشغيل الاختبارات بالكامل مع تقرير التغطية:
```powershell
.\venv\Scripts\pytest.exe
```

### فحص جودة وتنسيق الكود عبر Ruff:
```powershell
.\venv\Scripts\ruff.exe check .
```

---

## ☁️ النشر على Streamlit Community Cloud (Deployment)

1. **إعداد مستودع GitHub**: ارفع الكود إلى مستودع GitHub (مع استثناء ملفات الأسرار وفقاً لـ `.gitignore`).
2. **إعداد قاعدة البيانات (في حال استخدام Supabase)**:
   - افتح لوحة تحكم مشروع Supabase.
   - توجه إلى **SQL Editor** وشغّل محتويات الملف `supabase/schema.sql` لإنشاء الجداول وسياسات الـ RLS وحاوية التخزين.
3. **النشر على Streamlit Cloud**:
   - اربط حساب GitHub مع [Streamlit Community Cloud](https://share.streamlit.io/).
   - اختر المستودع، وحدد المسار الرئيسي: `app.py`.
   - في إعدادات التطبيق **App Settings -> Secrets**، الصق إعداداتك من `.streamlit/secrets.toml.example` بما فيها مفتاح `GEMINI_API_KEY` أو `LLM_API_KEY`.
   - اضغط **Deploy**.

---

## 🔒 رخصة الخطوط والمصادر / Licenses & Credits
- **Amiri Font**: مرخص بموجب رخصة الخطوط المفتوحة SIL Open Font License (OFL).
- تم بناء النظام وفق معايير الأمان لمنع هجمات حقن التعليمات وضمان العزل التام لبيانات الشركات.

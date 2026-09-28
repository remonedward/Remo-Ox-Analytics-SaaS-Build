from __future__ import annotations

"""Internationalisation (i18n) utilities for REMO_OX Analytics.

Supports Arabic (``"ar"``) and English (``"en"``). Arabic is the default
language and is displayed in RTL layout.

Usage::

    from core.i18n import t, inject_rtl_css

    lang = "ar"
    inject_rtl_css(lang)
    st.title(t("app_title", lang))
    st.write(t("upload_error_size", lang, max_mb=10))
"""


# ---------------------------------------------------------------------------
# String catalogue
# ---------------------------------------------------------------------------

#: Full translation catalogue keyed by language code → key → string.
#: Arabic strings use real Modern Standard Arabic.
#: Strings may contain ``{placeholder}`` format fields consumed by :func:`t`.
STRINGS: dict[str, dict[str, str]] = {
    "ar": {
        # ------------------------------------------------------------------
        # App
        # ------------------------------------------------------------------
        "app_title": "REMO_OX Analytics",
        "tagline": "تحليلات الأعمال الذكية",
        "loading": "جارٍ التحميل...",
        "error_generic": "حدث خطأ. يرجى المحاولة مرة أخرى.",
        "success": "تمت العملية بنجاح",
        "no_data": "لا توجد بيانات للعرض",
        "no_datasets": "لا توجد ملفات بيانات. ابدأ برفع ملف Excel.",
        "save": "حفظ",
        "cancel": "إلغاء",
        "delete": "حذف",
        "confirm": "تأكيد",
        "back": "رجوع",
        "next": "التالي",
        "close": "إغلاق",
        "search": "بحث",
        "filter": "تصفية",
        "reset": "إعادة تعيين",
        "refresh": "تحديث",
        "view_details": "عرض التفاصيل",
        "copy": "نسخ",
        "copied": "تم النسخ",
        "yes": "نعم",
        "no": "لا",
        "unknown": "غير معروف",
        "optional": "اختياري",
        "required": "مطلوب",
        "beta": "تجريبي",
        # ------------------------------------------------------------------
        # Authentication
        # ------------------------------------------------------------------
        "login": "تسجيل الدخول",
        "signup": "إنشاء حساب جديد",
        "logout": "تسجيل الخروج",
        "email": "البريد الإلكتروني",
        "password": "كلمة المرور",
        "forgot_password": "نسيت كلمة المرور؟",
        "reset_password": "إعادة تعيين كلمة المرور",
        "email_confirmation_sent": "تم إرسال رسالة تأكيد إلى بريدك الإلكتروني",
        "account_inactive": "حسابك غير نشط. يرجى التواصل مع الدعم.",
        "login_failed": "البريد الإلكتروني أو كلمة المرور غير صحيحة.",
        "signup_failed": "تعذّر إنشاء الحساب. يرجى المحاولة مرة أخرى.",
        "password_too_short": "يجب أن تتكوّن كلمة المرور من 8 أحرف على الأقل.",
        "email_invalid": "صيغة البريد الإلكتروني غير صحيحة.",
        "session_expired": "انتهت صلاحية الجلسة. يرجى تسجيل الدخول من جديد.",
        "not_authorized": "ليس لديك صلاحية للوصول إلى هذه الصفحة.",
        # ------------------------------------------------------------------
        # Upload
        # ------------------------------------------------------------------
        "upload_title": "رفع ملف البيانات",
        "upload_prompt": "اختر ملف Excel (.xlsx) للرفع",
        "upload_success": "تم رفع الملف بنجاح",
        "upload_processing": "جارٍ معالجة الملف...",
        "upload_error_type": "يجب أن يكون الملف بصيغة .xlsx فقط",
        "upload_error_size": "حجم الملف يتجاوز الحد المسموح ({max_mb} ميغابايت)",
        "upload_error_rows": "عدد الصفوف يتجاوز الحد المسموح ({max_rows} صف)",
        "upload_error_cols": "عدد الأعمدة يتجاوز الحد المسموح ({max_cols} عمود)",
        "upload_error_zipbomb": "رُفض الملف لأسباب أمنية. يرجى رفع ملف Excel صحيح.",
        "upload_error_corrupt": "الملف تالف أو غير صالح",
        "upload_error_magic": "الملف لا يحتوي على ترويسات ZIP/XLSX صحيحة. قد يكون الملف تالفاً.",
        "upload_replace_confirm": "يوجد ملف بيانات مرفوع بالفعل. هل تريد استبداله؟",
        "upload_sheet_preview": "معاينة الأوراق: {sheets}",
        "upload_rows_cols": "{rows} صف × {cols} عمود",
        # ------------------------------------------------------------------
        # Column Mapping
        # ------------------------------------------------------------------
        "mapping_title": "تحديد أعمدة البيانات",
        "mapping_instructions": "يرجى تأكيد تحديد الأعمدة للأدوار المختلفة",
        "mapping_confirm": "تأكيد التحديد",
        "mapping_auto_detected": "تم تحديد الأعمدة تلقائياً. يرجى المراجعة والتأكيد.",
        "mapping_manual_needed": "لم يتمكن النظام من تحديد بعض الأعمدة تلقائياً. يرجى تحديدها يدوياً.",
        "mapping_role_date": "التاريخ",
        "mapping_role_product": "المنتج / الصنف",
        "mapping_role_category": "الفئة",
        "mapping_role_customer": "العميل",
        "mapping_role_quantity": "الكمية",
        "mapping_role_unit_price": "سعر الوحدة",
        "mapping_role_revenue": "الإيراد / المبيعات",
        "mapping_role_unit_cost": "تكلفة الوحدة",
        "mapping_role_cost": "التكلفة",
        "mapping_role_expense_amount": "مبلغ المصروف",
        "mapping_role_stock_qty": "كمية المخزون",
        "mapping_role_last_movement_date": "تاريخ آخر حركة",
        "mapping_role_invoice_amount": "مبلغ الفاتورة",
        "mapping_role_paid_amount": "المبلغ المدفوع",
        "mapping_role_due_date": "تاريخ الاستحقاق",
        "mapping_role_invoice_date": "تاريخ الفاتورة",
        "mapping_role_supplier": "المورّد",
        "mapping_role_branch": "الفرع / الموقع",
        "mapping_role_currency": "العملة",
        "mapping_select_column": "اختر العمود...",
        "mapping_not_applicable": "لا ينطبق",
        "mapping_sheet_label": "الورقة: {sheet}",
        # ------------------------------------------------------------------
        # Reports
        # ------------------------------------------------------------------
        "reports_title": "التقارير",
        "report_sales_overview": "نظرة عامة على المبيعات",
        "report_top_products": "أفضل المنتجات",
        "report_slow_inventory": "المخزون بطيء الحركة",
        "report_receivables_aging": "تقادم المديونيات",
        "report_expense_breakdown": "تفصيل المصروفات",
        "report_missing_roles": "هذا التقرير يتطلب تحديد الأعمدة التالية: {roles}",
        "report_date_range": "الفترة الزمنية: {start} — {end}",
        "report_generated_on": "تاريخ التقرير: {date}",
        "report_currency": "العملة: {currency}",
        "report_total": "الإجمالي",
        "report_average": "المتوسط",
        "report_count": "العدد",
        "report_growth": "النمو ({period})",
        "show_calculation": "عرض طريقة الحساب",
        "hide_calculation": "إخفاء طريقة الحساب",
        "export_pdf": "تصدير PDF",
        "export_excel": "تصدير Excel",
        "generate_ai_summary": "توليد ملخص ذكي بالذكاء الاصطناعي",
        "top_n_label": "عرض أفضل {n}",
        "period_monthly": "شهري",
        "period_quarterly": "ربع سنوي",
        "period_yearly": "سنوي",
        "period_weekly": "أسبوعي",
        "days_overdue": "{days} يوم تأخير",
        "aging_bucket_current": "جارية",
        "aging_bucket_30": "1–30 يوم",
        "aging_bucket_60": "31–60 يوم",
        "aging_bucket_90": "61–90 يوم",
        "aging_bucket_90plus": "أكثر من 90 يوم",
        "slow_moving_threshold": "حركة أخيرة: أكثر من {days} يوم",
        # ------------------------------------------------------------------
        # AI Assistant
        # ------------------------------------------------------------------
        "ai_title": "المساعد الذكي",
        "ai_placeholder": "اسأل عن بياناتك... مثال: ما إجمالي المبيعات الشهرية؟",
        "ai_thinking": "جارٍ التحليل...",
        "ai_consent_title": "إشعار الخصوصية",
        "ai_consent_body": (
            "للإجابة على أسئلتك، يتم إرسال ملخصات إحصائية مجمّعة من بياناتك "
            "(ليس البيانات الخام) إلى مزود خدمة الذكاء الاصطناعي. "
            "لا يتم إرسال أي بيانات شخصية أو صفوف من ملفك."
        ),
        "ai_consent_accept": "أوافق وأبدأ",
        "ai_consent_decline": "لا أوافق",
        "ai_quota_exhausted": (
            "لقد استنفدت حصتك الشهرية من رسائل الذكاء الاصطناعي ({limit} رسالة). "
            "التقارير التفصيلية لا تزال متاحة."
        ),
        "ai_quota_remaining": "متبقي {remaining} رسالة من أصل {limit} هذا الشهر",
        "ai_error_unavailable": (
            "خدمة الذكاء الاصطناعي غير متاحة حالياً. "
            "يمكنك الاستمرار في استخدام التقارير التفصيلية."
        ),
        "ai_rate_limited": "يرجى الانتظار قليلاً قبل إرسال رسالة جديدة.",
        "ai_no_data": "يرجى رفع ملف بيانات أولاً قبل استخدام المساعد الذكي.",
        "ai_source_label": "المصدر",
        "ai_feedback_helpful": "مفيد",
        "ai_feedback_not_helpful": "غير مفيد",
        # ------------------------------------------------------------------
        # Account & Billing
        # ------------------------------------------------------------------
        "account_title": "حسابي",
        "plan_current": "خطتك الحالية: {plan}",
        "plan_trial": "تجريبية",
        "plan_starter": "المبتدئ",
        "plan_pro": "الاحترافية",
        "plan_enterprise": "المؤسسات",
        "plan_upgrade": "ترقية الخطة",
        "plan_expires": "تنتهي في: {date}",
        "usage_datasets": "ملفات البيانات: {used} من {limit}",
        "usage_ai_messages": "رسائل الذكاء الاصطناعي: {used} من {limit} هذا الشهر",
        "delete_my_data": "حذف جميع بياناتي",
        "delete_confirm": "هل أنت متأكد؟ هذا الإجراء لا يمكن التراجع عنه.",
        "data_deleted": "تم حذف جميع بياناتك بنجاح.",
        "change_password": "تغيير كلمة المرور",
        "change_language": "تغيير اللغة",
        # ------------------------------------------------------------------
        # Onboarding
        # ------------------------------------------------------------------
        "onboarding_step1_title": "الخطوة 1: رفع ملف البيانات",
        "onboarding_step1_body": "ابدأ برفع ملف Excel (.xlsx) يحتوي على بيانات مبيعاتك أو مخزونك أو مصروفاتك.",
        "onboarding_step2_title": "الخطوة 2: تحديد الأعمدة",
        "onboarding_step2_body": "سيقوم النظام تلقائياً بتحديد الأعمدة ذات الصلة. راجع التحديد وأكّده.",
        "onboarding_step3_title": "الخطوة 3: استعراض التقارير",
        "onboarding_step3_body": "اطّلع على تقاريرك التفصيلية: المبيعات، المخزون، المديونيات، والمصروفات.",
        "onboarding_step4_title": "الخطوة 4: اسأل المساعد الذكي",
        "onboarding_step4_body": "استخدم المساعد الذكي لطرح أسئلة مباشرة على بياناتك والحصول على إجابات فورية.",
        "onboarding_skip": "تخطّي الإرشادات",
        "onboarding_complete": "ابدأ الاستخدام",
        # ------------------------------------------------------------------
        # Admin panel
        # ------------------------------------------------------------------
        "admin_title": "لوحة الإدارة",
        "admin_users": "إدارة المستخدمين",
        "admin_system_health": "صحة النظام",
        "admin_config_warnings": "تحذيرات الإعدادات",
        "admin_no_warnings": "جميع الإعدادات صحيحة.",
        "admin_plan_change": "تغيير خطة المستخدم",
        "admin_user_id_label": "معرّف المستخدم",
        "admin_new_plan_label": "الخطة الجديدة",
        "admin_plan_updated": "تم تحديث الخطة بنجاح.",
        # ------------------------------------------------------------------
        # Errors & status
        # ------------------------------------------------------------------
        "error_network": "تعذّر الاتصال بالخادم. يرجى التحقق من اتصالك بالإنترنت.",
        "error_permission": "ليس لديك صلاحية لأداء هذا الإجراء.",
        "error_not_found": "العنصر المطلوب غير موجود.",
        "error_timeout": "انتهت مهلة الطلب. يرجى المحاولة مرة أخرى.",
        "error_data_parse": "تعذّر معالجة البيانات. يرجى التحقق من صحة الملف.",
        "status_ready": "جاهز",
        "status_processing": "قيد المعالجة",
        "status_done": "مكتمل",
        "status_failed": "فشل",
        "status_pending": "قيد الانتظار",
    },
    "en": {
        # ------------------------------------------------------------------
        # App
        # ------------------------------------------------------------------
        "app_title": "REMO_OX Analytics",
        "tagline": "Smart Business Analytics",
        "loading": "Loading...",
        "error_generic": "An error occurred. Please try again.",
        "success": "Operation completed successfully",
        "no_data": "No data to display",
        "no_datasets": "No datasets found. Start by uploading an Excel file.",
        "save": "Save",
        "cancel": "Cancel",
        "delete": "Delete",
        "confirm": "Confirm",
        "back": "Back",
        "next": "Next",
        "close": "Close",
        "search": "Search",
        "filter": "Filter",
        "reset": "Reset",
        "refresh": "Refresh",
        "view_details": "View Details",
        "copy": "Copy",
        "copied": "Copied",
        "yes": "Yes",
        "no": "No",
        "unknown": "Unknown",
        "optional": "Optional",
        "required": "Required",
        "beta": "Beta",
        # ------------------------------------------------------------------
        # Authentication
        # ------------------------------------------------------------------
        "login": "Sign In",
        "signup": "Create Account",
        "logout": "Sign Out",
        "email": "Email",
        "password": "Password",
        "forgot_password": "Forgot Password?",
        "reset_password": "Reset Password",
        "email_confirmation_sent": "Confirmation email sent. Please check your inbox.",
        "account_inactive": "Your account is inactive. Please contact support.",
        "login_failed": "Incorrect email or password.",
        "signup_failed": "Could not create account. Please try again.",
        "password_too_short": "Password must be at least 8 characters.",
        "email_invalid": "Invalid email address format.",
        "session_expired": "Your session has expired. Please sign in again.",
        "not_authorized": "You do not have permission to access this page.",
        # ------------------------------------------------------------------
        # Upload
        # ------------------------------------------------------------------
        "upload_title": "Upload Data File",
        "upload_prompt": "Choose an Excel file (.xlsx) to upload",
        "upload_success": "File uploaded successfully",
        "upload_processing": "Processing file...",
        "upload_error_type": "Only .xlsx files are accepted",
        "upload_error_size": "File size exceeds the limit ({max_mb} MB)",
        "upload_error_rows": "Row count exceeds the limit ({max_rows} rows)",
        "upload_error_cols": "Column count exceeds the limit ({max_cols} columns)",
        "upload_error_zipbomb": "File rejected for security reasons. Please upload a valid Excel file.",
        "upload_error_corrupt": "File is corrupt or invalid",
        "upload_error_magic": "File does not have valid ZIP/XLSX headers. The file may be corrupt.",
        "upload_replace_confirm": "A dataset is already uploaded. Do you want to replace it?",
        "upload_sheet_preview": "Sheets found: {sheets}",
        "upload_rows_cols": "{rows} rows × {cols} columns",
        # ------------------------------------------------------------------
        # Column Mapping
        # ------------------------------------------------------------------
        "mapping_title": "Map Data Columns",
        "mapping_instructions": "Please confirm the column assignments for each role",
        "mapping_confirm": "Confirm Mapping",
        "mapping_auto_detected": "Columns were automatically detected. Please review and confirm.",
        "mapping_manual_needed": "Some columns could not be auto-detected. Please map them manually.",
        "mapping_role_date": "Date",
        "mapping_role_product": "Product / Item",
        "mapping_role_category": "Category",
        "mapping_role_customer": "Customer",
        "mapping_role_quantity": "Quantity",
        "mapping_role_unit_price": "Unit Price",
        "mapping_role_revenue": "Revenue / Sales",
        "mapping_role_unit_cost": "Unit Cost",
        "mapping_role_cost": "Cost",
        "mapping_role_expense_amount": "Expense Amount",
        "mapping_role_stock_qty": "Stock Quantity",
        "mapping_role_last_movement_date": "Last Movement Date",
        "mapping_role_invoice_amount": "Invoice Amount",
        "mapping_role_paid_amount": "Paid Amount",
        "mapping_role_due_date": "Due Date",
        "mapping_role_invoice_date": "Invoice Date",
        "mapping_role_supplier": "Supplier",
        "mapping_role_branch": "Branch / Location",
        "mapping_role_currency": "Currency",
        "mapping_select_column": "Select column...",
        "mapping_not_applicable": "Not Applicable",
        "mapping_sheet_label": "Sheet: {sheet}",
        # ------------------------------------------------------------------
        # Reports
        # ------------------------------------------------------------------
        "reports_title": "Reports",
        "report_sales_overview": "Sales Overview",
        "report_top_products": "Top Products",
        "report_slow_inventory": "Slow-Moving Inventory",
        "report_receivables_aging": "Receivables Aging",
        "report_expense_breakdown": "Expense Breakdown",
        "report_missing_roles": "This report requires the following column mappings: {roles}",
        "report_date_range": "Period: {start} — {end}",
        "report_generated_on": "Report date: {date}",
        "report_currency": "Currency: {currency}",
        "report_total": "Total",
        "report_average": "Average",
        "report_count": "Count",
        "report_growth": "Growth ({period})",
        "show_calculation": "Show Calculation",
        "hide_calculation": "Hide Calculation",
        "export_pdf": "Export PDF",
        "export_excel": "Export Excel",
        "generate_ai_summary": "Generate AI Summary",
        "top_n_label": "Show Top {n}",
        "period_monthly": "Monthly",
        "period_quarterly": "Quarterly",
        "period_yearly": "Yearly",
        "period_weekly": "Weekly",
        "days_overdue": "{days} days overdue",
        "aging_bucket_current": "Current",
        "aging_bucket_30": "1–30 days",
        "aging_bucket_60": "31–60 days",
        "aging_bucket_90": "61–90 days",
        "aging_bucket_90plus": "Over 90 days",
        "slow_moving_threshold": "Last moved: over {days} days ago",
        # ------------------------------------------------------------------
        # AI Assistant
        # ------------------------------------------------------------------
        "ai_title": "AI Assistant",
        "ai_placeholder": "Ask about your data... e.g. What are the monthly sales totals?",
        "ai_thinking": "Analyzing...",
        "ai_consent_title": "Privacy Notice",
        "ai_consent_body": (
            "To answer your questions, aggregated statistical summaries from your data "
            "(not raw data) are sent to an AI provider. "
            "No personal data or raw file rows are transmitted."
        ),
        "ai_consent_accept": "I Agree & Continue",
        "ai_consent_decline": "I Decline",
        "ai_quota_exhausted": (
            "You have used your monthly AI message quota ({limit} messages). "
            "Detailed reports are still available."
        ),
        "ai_quota_remaining": "{remaining} of {limit} messages remaining this month",
        "ai_error_unavailable": (
            "The AI assistant is currently unavailable. "
            "You can still use the detailed reports."
        ),
        "ai_rate_limited": "Please wait a moment before sending another message.",
        "ai_no_data": "Please upload a dataset before using the AI assistant.",
        "ai_source_label": "Source",
        "ai_feedback_helpful": "Helpful",
        "ai_feedback_not_helpful": "Not Helpful",
        # ------------------------------------------------------------------
        # Account & Billing
        # ------------------------------------------------------------------
        "account_title": "My Account",
        "plan_current": "Your current plan: {plan}",
        "plan_trial": "Trial",
        "plan_starter": "Starter",
        "plan_pro": "Pro",
        "plan_enterprise": "Enterprise",
        "plan_upgrade": "Upgrade Plan",
        "plan_expires": "Expires: {date}",
        "usage_datasets": "Datasets: {used} of {limit}",
        "usage_ai_messages": "AI messages: {used} of {limit} this month",
        "delete_my_data": "Delete All My Data",
        "delete_confirm": "Are you sure? This action cannot be undone.",
        "data_deleted": "All your data has been deleted successfully.",
        "change_password": "Change Password",
        "change_language": "Change Language",
        # ------------------------------------------------------------------
        # Onboarding
        # ------------------------------------------------------------------
        "onboarding_step1_title": "Step 1: Upload Your Data File",
        "onboarding_step1_body": "Start by uploading an Excel (.xlsx) file containing your sales, inventory, or expense data.",
        "onboarding_step2_title": "Step 2: Map Your Columns",
        "onboarding_step2_body": "The system will automatically detect relevant columns. Review and confirm the mapping.",
        "onboarding_step3_title": "Step 3: Explore Your Reports",
        "onboarding_step3_body": "View detailed reports: Sales, Inventory, Receivables Aging, and Expense Breakdown.",
        "onboarding_step4_title": "Step 4: Ask the AI Assistant",
        "onboarding_step4_body": "Use the AI assistant to ask plain-language questions about your data and get instant answers.",
        "onboarding_skip": "Skip Tutorial",
        "onboarding_complete": "Get Started",
        # ------------------------------------------------------------------
        # Admin panel
        # ------------------------------------------------------------------
        "admin_title": "Admin Panel",
        "admin_users": "User Management",
        "admin_system_health": "System Health",
        "admin_config_warnings": "Configuration Warnings",
        "admin_no_warnings": "All settings are valid.",
        "admin_plan_change": "Change User Plan",
        "admin_user_id_label": "User ID",
        "admin_new_plan_label": "New Plan",
        "admin_plan_updated": "Plan updated successfully.",
        # ------------------------------------------------------------------
        # Errors & status
        # ------------------------------------------------------------------
        "error_network": "Could not reach the server. Please check your internet connection.",
        "error_permission": "You do not have permission to perform this action.",
        "error_not_found": "The requested item was not found.",
        "error_timeout": "The request timed out. Please try again.",
        "error_data_parse": "Could not process the data. Please check the file.",
        "status_ready": "Ready",
        "status_processing": "Processing",
        "status_done": "Done",
        "status_failed": "Failed",
        "status_pending": "Pending",
    },
}

# ---------------------------------------------------------------------------
# Translation function
# ---------------------------------------------------------------------------

#: Fallback language used when a key is absent in the requested language.
_FALLBACK_LANG: str = "en"


def t(key: str, lang: str | None = None, **kwargs: object) -> str:
    """Look up a translated string and format it with *kwargs*.

    Falls back to English if the key is missing in the requested language.
    Falls back to the bare *key* string if the key is missing in English too
    (so the UI never raises a ``KeyError`` in production).

    Args:
        key: Translation key from :data:`STRINGS`.
        lang: Language code (``"ar"`` or ``"en"``). When ``None``, defaults
            to ``"ar"`` (the application default language).
        **kwargs: Named format arguments substituted into the translated
            string using :meth:`str.format_map`. Unrecognised keys are
            silently ignored.

    Returns:
        Translated (and formatted) string.

    Example::

        t("upload_error_size", "ar", max_mb=10)
        # → "حجم الملف يتجاوز الحد المسموح (10 ميغابايت)"

        t("report_missing_roles", "en", roles="Date, Revenue")
        # → "This report requires the following column mappings: Date, Revenue"
    """
    resolved_lang: str = lang if lang in STRINGS else _FALLBACK_LANG

    # Try requested language, then English fallback, then bare key.
    catalogue = STRINGS.get(resolved_lang, {})
    template = catalogue.get(key)

    if template is None and resolved_lang != _FALLBACK_LANG:
        template = STRINGS.get(_FALLBACK_LANG, {}).get(key)

    if template is None:
        return key  # Last resort — return the raw key so UI is not broken.

    if not kwargs:
        return template

    try:
        return template.format_map(kwargs)
    except (KeyError, ValueError):
        # Return unformatted template rather than crashing.
        return template


# ---------------------------------------------------------------------------
# RTL CSS helpers
# ---------------------------------------------------------------------------

#: CSS injected into the Streamlit app when the language is Arabic.
_RTL_CSS: str = """
<style>
/* ── Global RTL layout ──────────────────────────────────────────── */
html, body, [class*="css"] {
    direction: rtl;
    text-align: right;
    font-family: 'Segoe UI', Tahoma, Arial, sans-serif;
}

/* ── Streamlit-specific overrides ───────────────────────────────── */
.stApp {
    direction: rtl;
}

/* Sidebar */
section[data-testid="stSidebar"] {
    direction: rtl;
    text-align: right;
}

/* Markdown / text elements */
.stMarkdown, .stText, p, h1, h2, h3, h4, h5, h6, li {
    direction: rtl;
    text-align: right;
}

/* Tables */
.stDataFrame, table {
    direction: rtl;
    text-align: right;
}

/* Input widgets */
.stTextInput > label,
.stSelectbox > label,
.stMultiselect > label,
.stNumberInput > label,
.stDateInput > label,
.stTextArea > label {
    direction: rtl;
    text-align: right;
}

.stTextInput input,
.stTextArea textarea,
.stSelectbox select {
    direction: rtl;
    text-align: right;
}

/* Buttons */
.stButton > button {
    direction: rtl;
}

/* File uploader */
.stFileUploader > label,
.stFileUploader > div {
    direction: rtl;
    text-align: right;
}

/* Metric widgets */
.stMetric {
    direction: rtl;
    text-align: right;
}

/* Alert / info boxes */
.stAlert {
    direction: rtl;
    text-align: right;
}

/* Expander */
.streamlit-expanderHeader {
    direction: rtl;
    text-align: right;
}

/* Tabs */
.stTabs [data-baseweb="tab-list"] {
    direction: rtl;
}

/* Number inputs — keep digits LTR inside an RTL container */
.stNumberInput input {
    direction: ltr;
    text-align: right;
}

/* Charts — matplotlib/plotly figures are not affected by CSS direction */
</style>
"""


def get_rtl_css() -> str:
    """Return the RTL CSS string for Arabic layout.

    The returned string is ready to be passed to
    ``st.markdown(..., unsafe_allow_html=True)``.

    Returns:
        HTML ``<style>`` block enforcing right-to-left layout.

    Example::

        if lang == "ar":
            st.markdown(get_rtl_css(), unsafe_allow_html=True)
    """
    return _RTL_CSS


def inject_rtl_css(lang: str) -> None:
    """Inject RTL CSS into the Streamlit page when *lang* is Arabic.

    This is a convenience wrapper that imports Streamlit lazily so the i18n
    module can be imported in test contexts without a Streamlit server.

    Args:
        lang: Language code. RTL CSS is only injected when *lang* == ``"ar"``.

    Example::

        from core.i18n import inject_rtl_css
        inject_rtl_css(session_lang)   # call once near the top of each page
    """
    if lang != "ar":
        return

    try:
        import streamlit as st

        st.markdown(get_rtl_css(), unsafe_allow_html=True)
    except Exception:
        # Streamlit not running (e.g. unit test context) — silently skip.
        pass

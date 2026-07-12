# دليل القبول للإصدار الأول

تشغّل بوابة القبول الآلية `uv run ruff check .` ثم `uv run pytest -q`.
النتيجة الحالية: **53 اختباراً ناجحاً**. لا تستخدم الاختبارات مفاتيح Gate.io أو
ترسل طلبات تداول حقيقية.

| المعيار | الدليل الآلي | التحقق الخارجي المتبقي |
| --- | --- | --- |
| TEST-001–003 | `tests/process/test_engine_ui_lifecycle.py`, `test_exchange_safety_api.py` | WinSW وRestart Windows |
| TEST-004–008 | اختبارات Paper API والتحليل والقرار | لا شيء خارجياً |
| TEST-009–010 | اختبارات دورة Paper Limit وحماية حالة التنفيذ | Testnet adapter مع حساب حقيقي |
| TEST-011–012 | `test_paper_market_entry_api.py`, `test_paper_operations_api.py` | لا شيء خارجياً |
| TEST-013–018 | `test_paper_operations_api.py`, `test_exchange_safety_api.py` | Testnet partial fills/reconciliation |
| TEST-019–021 | `test_paper_operations_api.py`, `test_runtime_api.py` | PostgreSQL/VPS restart |
| TEST-022 | `test_paper_operations_api.py` | لا شيء خارجياً |
| TEST-023–024 | `test_exchange_safety_api.py` | مراجعة Live للقراءة فقط |
| TEST-025 | `test_paper_operations_api.py` | لا شيء خارجياً |
| TEST-026–027 | `test_exchange_safety_api.py` | لا شيء خارجياً؛ لا تنفذ أمراً Live |

## قرارات الإصدار

- Testnet وLive يعرضان فقط حالة مصالحة منقّحة عبر واجهة محلية. لا تقبل الواجهة
  مفاتيح أو توقيعات أو حمولة Gate.io خام. لا يثق المحرك بحالة يرسلها العميل؛
  يتطلب adapter محقوناً من جهة المحرك.
- Live يبقى مقفلاً عند الإنشاء وإيقاف الطوارئ، ولا يفك إلا بتأكيد `LIVE` وبحالة
  مصالحة جاهزة. دليل Paper/Testnet استشاري فقط.
- نقطة تنفيذ Live محجوبة افتراضياً عندما لا يوجد adapter مهيأ؛ تعيد خطأ آمن ولا
  ترسل طلباً. تنفيذ Gate.io v4 مغطى بعقود mock موقعة واختبارات دخول/إلغاء/إغلاق
  وحماية؛ التحقق الخارجي الحقيقي ما زال شرط قبول منفصل ولا يدّعي هذا الدليل حدوثه.
- المواصفة البصرية وخريطة الصفحات موجودة في [مواصفة الواجهة العربية](ui-spec-ar.md).

## أدلة يدوية مطلوبة قبل التشغيل الفعلي

القائمة النهائية في `docs/operations.md` هي المرجع: حساب Testnet، WinSW/VPS،
نسخة PostgreSQL واستعادتها، ومراجعة RTL عبر Remote Desktop. هذه أنشطة خارجية
تتطلب صلاحيات المستخدم ولا تمثل فشلاً للاختبارات الآلية أو سبباً لتفعيل Live.

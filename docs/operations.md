# عمليات النشر والاستعادة

## قواعد الأمان

- Live يبدأ دائماً في **Live Locked**. لا تفك القفل تلقائياً ولا تضغط تفعيل Live
  من دون فحص الحساب الحالي.
- لا تضع `.env` أو مفاتيح Gate.io أو نسخ قاعدة البيانات في المستودع أو حزمة
  PyInstaller. امنح ملف الإعداد أذونات قراءة للمشغّل فقط.
- يتصل المحرك وPostgreSQL محلياً فقط. واجهة FastAPI مقيدة بـ `127.0.0.1`.
- لا يعد تشغيل اختبار Testnet أو سجلات الجاهزية تصريحاً لتفعيل Live؛ هي أدلة
  استشارية فقط.

## تثبيت Windows

1. أنشئ `C:\RangeBot\engine` و`C:\RangeBot\ui` و`C:\RangeBot\config` و`C:\RangeBot\logs` و`C:\RangeBot\service`.
2. ابنِ حزمتين منفصلتين: `uv run pyinstaller deploy/engine.spec` و
   `uv run pyinstaller deploy/ui.spec`، ثم انسخ مخرجات `onedir` المناسبة.
3. انسخ `.env.example` إلى `C:\RangeBot\config\.env` وأدخل اتصال PostgreSQL
   المحلي ومفاتيح منفصلة ذات صلاحية تداول فقط وwithdrawals معطلة. لا تدخل مفاتيح
   إن كنت تجري اختبار Paper فقط.
4. ضع WinSW و[RangeBot.Engine.xml](../deploy/RangeBot.Engine.xml) في مجلد الخدمة
   واضبط متغير بيئة `RANGEBOT_DATABASE_URL` في حساب الخدمة. ثبّت الخدمة وشغّلها.
   يمكن استخدام `deploy\install-service.ps1 -InstallRoot C:\RangeBot` من نافذة
   PowerShell مرتفعة الصلاحيات بعد وضع WinSW والملف XML في مجلد الخدمة.
5. افتح `rangebot-control.exe` بصورة منفصلة؛ أغلقه ثم تحقق أن خدمة المحرك بقيت
   تعمل. إيقاف الخدمة لا يغلق مركزاً قائماً تلقائياً.

## نسخ PostgreSQL واستعادته

نفّذ ذلك أثناء توقف الخدمة المقصود وبعد توثيق حالة Gate.io. لا تضع كلمات المرور
في سطر الأوامر أو السجل.

```powershell
# أدخل كلمة المرور في موجه PostgreSQL أو من مدير أسرار؛ لا تحفظها في ملف أو سجل.
pg_dump --format=custom --file C:\RangeBot\backup\rangebot.backup --host 127.0.0.1 --username rangebot rangebot
pg_restore --clean --if-exists --host 127.0.0.1 --username rangebot --dbname rangebot C:\RangeBot\backup\rangebot.backup
```

توجد أوامر مغلفة وآمنة في `deploy\backup-postgresql.ps1` و
`deploy\restore-postgresql.ps1`. تتطلب الاستعادة التأكيد الحرفي
`RESTORE RANGEBOT` ولا تخزن كلمة مرور.

بعد الاستعادة: شغّل خدمة المحرك، تحقق من ترحيلات القاعدة، نفّذ مصالحة Gate.io
للمراكز والأوامر، تحقق من TP/SL، واترك الدخول محظوراً حتى تنجح المصالحة. سجل
النتيجة كدليل تشغيل، لا كسماح تلقائي لـ Live.
ابدأ التشغيل الأول بعد الاستعادة مع `--restored-state`؛ يمسح المحرك جاهزية
Testnet/Live المخزنة ويبقي الدخول محظوراً حتى تصل مصالحة وحماية جديدتان.

## فحوصات خارجية لا يمكن أتمتتها

- اتصال حساب Gate.io Testnet حقيقي ومصادقة WebSocket/REST.
- تثبيت WinSW وحساب خدمة على الـ VPS وإعادة تشغيل Windows.
- نسخة واستعادة PostgreSQL فعلية على قاعدة الإنتاج المحلية.
- مراجعة بصرية يدوية عبر Remote Desktop وخط عربي مختار.

كل تنفيذ طلب حقيقي يبقى قراراً يدوياً منفصلاً للمشغّل؛ لا تحتاج هذه الحزمة إلى
إرسال أمر Live للتحقق من القفل أو المصالحة للقراءة فقط.

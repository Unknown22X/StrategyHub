# Paper and Gate.io Testnet Trading Verification

هذا الدليل يتحقق من دورة التداول الكاملة من دون استخدام LIVE credentials أو LIVE Orders أو أموال حقيقية.

## Automated verification

من جذر المشروع على Windows:

```powershell
uv run pytest tests/integration/test_p0_5_trading_verification.py -q
```

يغطي الاختبار الآلي:

- اختيار Paper ثم التبديل الموثوق إلى Testnet.
- Testnet Credential status واختبار Credentials بعملية read-only.
- Reconciliation وstructured readiness.
- Preview ثم Submit عبر Central Order Manager.
- Position بعد التعبئة.
- Take Profit وStop Loss كأوامر reduce-only وبنفس Quantity.
- Protection check.
- Manual close والتأكد من عودة Position Quantity إلى صفر.
- Paper Take Profit trigger وPaper Stop Loss trigger كلٌ في حساب معزول.
- التأكد من عدم إنشاء Live adapter وعدم وجود Live snapshot.

الاختبار يستخدم `MockGateIoAdapter` وSQLite مؤقتة. لا يتصل بـ Gate.io ولا يستخدم أي Secret حقيقي.

## Manual Gate.io Testnet verification on Windows

هذه الخطوات مطلوبة مرة واحدة قبل اعتبار الاتصال الحقيقي بـ Gate Testnet مُتحققاً. استخدم API key من Gate.io Testnet فقط. لا تُدخل LIVE key في هذا الاختبار.

### 1. Safety preparation

1. افتح Gate.io Testnet وتأكد أن الحساب المعروض هو Testnet وليس الحساب الحقيقي.
2. أنشئ API key خاصاً بـ Testnet بأقل صلاحيات مطلوبة للتداول والقراءة، ومن دون Withdrawal permission.
3. افتح RangeBot على Windows وتأكد أن Environment الحالي هو Paper.
4. تأكد أن أي Live API key غير موجود أو لا تستخدمه أثناء هذا الاختبار.
5. استخدم أقل Quantity يسمح بها عقد Testnet المختار.

توقف فوراً إذا ظهر أي من التالي:

- Environment badge يعرض LIVE.
- Public REST أو exchange adapter يعرض Live أثناء العملية.
- نافذة تؤكد استخدام real funds.
- العقد أو الرصيد الظاهر يخص حساب Gate الحقيقي.

### 2. Store and test Testnet Credentials

1. افتح Gate Connection.
2. اختر Testnet.
3. أدخل Testnet API Key وAPI Secret واحفظهما في Windows Credential Manager.
4. اضغط Test Credentials.
5. يجب أن تظهر نتيجة read-only ناجحة، من دون إنشاء Order.

API equivalents:

```http
GET /v1/exchange/testnet/credentials
POST /v1/exchange/testnet/credentials/test
```

النتيجة المطلوبة:

```json
{
  "mode": "testnet",
  "configured": true
}
```

واختبار Credentials يجب أن يعيد `valid: true`.

### 3. Switch to Testnet and verify authoritative environment

1. اختر Testnet من Environment selector.
2. انتظر حتى تنتهي حالة Switching.
3. تحقق أن القيم التالية كلها Testnet:
   - Active Engine Environment
   - Exchange Adapter Environment
   - Public REST Environment
   - Public WebSocket Environment
   - Private WebSocket Environment
   - Credential Profile
4. لا تتابع إذا كانت أي طبقة تعرض Live أو mismatch.

API equivalents:

```http
POST /v1/runtime/environment/switch
Content-Type: application/json

{"environment":"testnet"}
```

ثم:

```http
GET /v1/runtime/environment
```

### 4. Reconciliation and readiness

1. شغّل Reconciliation.
2. انتظر حتى تكون Snapshot حديثة.
3. تحقق من:
   - `ready=true`
   - `refresh_in_progress=false`
   - لا يوجد `unmanaged_exchange_state`
   - One-way confirmed
   - Cross Margin confirmed
   - Risk Data ready
   - Protection ready
   - REST snapshot وPrivate Stream جاهزان
4. إذا كانت الحالة stale أو missing أو failed، لا ترسل Order.

```http
POST /v1/exchange/testnet/reconcile
GET /v1/exchange/testnet/reconciliation
```

### 5. Preview a minimum-size Testnet Order

1. اختر عقد USDT Perpetual واضحاً، مثل `BTC_USDT`، بعد التحقق من Contract Rules.
2. استخدم Minimum Quantity أو أقل Margin صالح يظهر في Preview.
3. اختر Leverage منخفضة، مثل 1x أو 2x، ما لم تتطلب قواعد الاختبار غير ذلك.
4. أنشئ Preview فقط.
5. تحقق من:
   - `can_submit=true`
   - Environment = Testnet
   - `uses_real_funds=false`
   - Quantity وPrice steps صحيحة
   - Estimated Margin والFees معقولة
   - Take Profit أعلى من Entry للـ Long أو أسفلها للـ Short
   - Stop Loss في الاتجاه المعاكس الصحيح
6. لا تتابع عند أي Validation Issue.

```http
POST /v1/manual-orders/preview
```

### 6. Submit and verify Position, Take Profit, and Stop Loss

1. أرسل Order باستخدام `safety_fingerprint` نفسه من أحدث Preview.
2. افتح Position في RangeBot وفي Gate.io Testnet.
3. تحقق أن Symbol وDirection وQuantity وLeverage متطابقة.
4. تحقق أن Take Profit موجود و`reduce_only=true`.
5. تحقق أن Stop Loss موجود و`reduce_only=true`.
6. يجب أن تكون Quantity لكل Protection Order مساوية للـ remaining Position Quantity، وألا تسمح بفتح Position عكسية.
7. شغّل Protection check وتأكد أنه لا ينشئ duplicate Protection Orders.

```http
POST /v1/manual-orders
GET /v1/exchange/testnet/state
POST /v1/exchange/testnet/protection/check
```

### 7. Close safely

1. أغلق Position من RangeBot باستخدام Manual close.
2. اكتب `CLOSE POSITION` حرفياً عند الطلب.
3. تحقق في RangeBot وفي Gate.io Testnet أن Position Quantity أصبحت صفراً.
4. تحقق أن Take Profit وStop Loss لم يعودا نشطين بعد الإغلاق.
5. شغّل Reconciliation مرة أخيرة وتأكد من عدم وجود unmanaged state.

```http
POST /v1/exchange/testnet/close
Content-Type: application/json

{"confirmation":"CLOSE POSITION"}
```

ثم:

```http
POST /v1/exchange/testnet/reconcile
GET /v1/exchange/testnet/state
```

### 8. Cleanup

1. أوقف أي Strategy أو pending Testnet Order.
2. فعّل Emergency Stop مؤقتاً إذا كانت هناك حالة غير متوقعة.
3. احذف Testnet Credentials من RangeBot عندما لا تعود مطلوبة.
4. لا تنقل Testnet Secret إلى ملفات `.env` أو logs أو screenshots.

## Verification record

سجّل عند التنفيذ اليدوي:

- Date/time and Windows machine
- RangeBot commit hash
- Testnet contract
- Testnet Order ID فقط
- Quantity and Leverage
- Reconciliation reason codes before and after
- Position, Take Profit, Stop Loss, and close results
- Confirmation that no Live key, Live Order, or real funds were used

## Current limitation

التحقق الآلي أعلاه مكتمل باستخدام المحاكي المحلي. لم تُستخدم في جلسة التطوير هذه Gate.io Testnet credentials حقيقية، ولم يتم تنفيذ interaction يدوي مع Windows service أو Gate.io Testnet UI. لذلك يبقى القسم اليدوي أعلاه مطلوباً للتحقق من الشبكة والحساب الحقيقيين في Testnet فقط.

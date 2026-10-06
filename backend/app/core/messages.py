"""User-facing strings in Arabic / English / Urdu (CLAUDE.md conventions).

The privacy text is served as `privacy` in `GET /api/v1/sources` (the About page, API_CONTRACT.md).
It includes the free-tier provider notice (DECISIONS D-15).
"""

from __future__ import annotations

Lang = str

DISCLAIMER: dict[Lang, str] = {
    "ar": "أداة آلية للتحقق من المصادر، وليست فتوى.",
    "en": "An automated source-verification tool, not a fatwa.",
    "ur": "یہ ذرائع کی جانچ کا ایک خودکار آلہ ہے، فتویٰ نہیں۔",
}

# SPEC §13 privacy text + free-tier provider notice (D-15).
PRIVACY: dict[Lang, str] = {
    "ar": (
        "تُحفظ نتيجة التحقق 24 ساعة لعرض التفاصيل والرد الجاهز ثم تُحذف. "
        "لا تُحفظ هوية المرسل ولا يُستنتج منها أي شيء عن معتقده. "
        "يعمل ميزان على الخطة المجانية لمزوّد النموذج اللغوي، وقد يستخدم المزوّد النصوص المُرسلة "
        "لتحسين خدماته؛ فلا تُرسل بيانات شخصية أو حساسة."
    ),
    "en": (
        "A check result is stored for 24 hours to show its details and the ready reply, then deleted. "
        "The sender's identity is not stored and nothing is inferred about their beliefs. "
        "Mizan runs on the free tier of its language-model provider, which may use submitted text to "
        "improve its services, so do not submit personal or sensitive information."
    ),
    "ur": (
        "جانچ کا نتیجہ تفصیلات اور تیار جواب دکھانے کے لیے 24 گھنٹے محفوظ رہتا ہے، پھر حذف کر دیا جاتا ہے۔ "
        "بھیجنے والے کی شناخت محفوظ نہیں کی جاتی اور اس سے اس کے عقیدے کے بارے میں کوئی نتیجہ اخذ نہیں کیا جاتا۔ "
        "میزان اپنے لسانی ماڈل فراہم کنندہ کے مفت پلان پر چلتا ہے، اور فراہم کنندہ بھیجے گئے متن کو اپنی خدمات "
        "بہتر بنانے کے لیے استعمال کر سکتا ہے؛ اس لیے ذاتی یا حساس معلومات نہ بھیجیں۔"
    ),
}


def localized(table: dict[Lang, str], lang: str | None) -> str:
    return table.get(lang or "ar", table["ar"])

# SPEC §8.4 message-level statuses.
NO_CLAIMS: dict[Lang, str] = {
    "ar": (
        "يتحقق ميزان من الآيات والأحاديث المنقولة في النص، ولم يجد في رسالتك آية أو حديثًا منسوبًا. "
        "للأسئلة العامة عن الإسلام راجع: byenah.com و islamhouse.com"
    ),
    "en": (
        "Mizan checks quoted verses and hadiths, and found none in your message. "
        "For general questions about Islam, see byenah.com and islamhouse.com."
    ),
    "ur": (
        "میزان پیغام میں نقل کی گئی آیات اور احادیث کی جانچ کرتا ہے، آپ کے پیغام میں کوئی آیت یا حدیث نہیں ملی۔ "
        "اسلام کے بارے میں عمومی سوالات کے لیے byenah.com اور islamhouse.com دیکھیں۔"
    ),
}

EVIDENCE_REQUEST: dict[Lang, str] = {
    "ar": (
        "ميزان لا يبحث عن أدلة ولا يقترح نصوصًا؛ هو يتحقق من نص منقول تُرسله إليه. "
        "لم نجد دليلًا مطابقًا يمكن تقديمه من المصادر المتاحة. للسؤال عن دليل مسألة ما، راجع أهل العلم المختصين."
    ),
    "en": (
        "Mizan does not search for or supply evidence; it verifies a quote you send it. "
        "We have no matching evidence to offer from the available sources. To ask for the evidence on an issue, "
        "please consult a qualified scholar."
    ),
    "ur": (
        "میزان دلائل تلاش یا فراہم نہیں کرتا؛ یہ آپ کے بھیجے ہوئے اقتباس کی جانچ کرتا ہے۔ "
        "دستیاب ذرائع سے پیش کرنے کے لیے کوئی مطابق دلیل نہیں ملی۔ کسی مسئلے کی دلیل کے لیے مستند اہلِ علم سے رجوع کریں۔"
    ),
}

REFERRAL: dict[Lang, str] = {
    "ar": (
        "ميزان أداة للتحقق من المصادر وليس جهة فتوى. لسؤالك عن حالتك الخاصة، راجع جهة إفتاء معتمدة أو عالمًا مؤهلًا "
        "في بلدك."
    ),
    "en": (
        "Mizan is a source-verification tool, not a fatwa service. For a ruling on your own situation, please "
        "consult a recognized fatwa authority or a qualified scholar in your country."
    ),
    "ur": (
        "میزان ذرائع کی جانچ کا آلہ ہے، فتویٰ دینے والا ادارہ نہیں۔ اپنی ذاتی صورتِ حال کے بارے میں حکم کے لیے اپنے ملک کے کسی "
        "معتبر دارالافتاء یا مستند عالم سے رجوع کریں۔"
    ),
}

LIMITS: dict[Lang, list[str]] = {
    "ar": [
        "يتحقق ميزان من الآيات والأحاديث فقط، ولا يتحقق من الأقوال المنسوبة إلى العلماء والصحابة.",
        "تعرض الأحكام كما وردت في المصادر دون ترجيح بين المحدّثين.",
        "قد لا يجد ميزان نصًا موجودًا إذا اختلفت صياغته كثيرًا أو لم يرد في المصادر المتاحة.",
    ],
    "en": [
        "Mizan checks verses and hadiths only; it does not verify sayings attributed to scholars or Companions.",
        "Gradings are shown as given by the sources, without preferring one scholar over another.",
        "Mizan may miss a text whose wording differs a lot, or that is not in the available sources.",
    ],
    "ur": [
        "میزان صرف آیات اور احادیث کی جانچ کرتا ہے، علما اور صحابہ سے منسوب اقوال کی نہیں۔",
        "احکام ذرائع کے مطابق بیان کیے جاتے ہیں، محدثین میں ترجیح کے بغیر۔",
        "اگر الفاظ بہت مختلف ہوں یا متن دستیاب ذرائع میں نہ ہو تو میزان اسے نہیں پا سکتا۔",
    ],
}

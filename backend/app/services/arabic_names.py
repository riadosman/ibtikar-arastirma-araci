"""Arabic-script person names.

Latin-script extraction accepts a phrase as a name when every word is capitalized. Arabic has
no capital letters, so that evidence is missing and generic headings ("أستاذ جامعي", "علم
البيانات") looked like names. Here a name must start with a common Arabic given name (or an
"عبد ..." compound) and contain no generic word. Unknown or rare names are missed on purpose:
extraction stays conservative.
"""

import re

ARABIC_LETTER = re.compile(r"[\u0600-\u06FF]")
# Letters only (after fold): no digits, punctuation or Latin characters.
ARABIC_WORD = re.compile(r"^[\u0621-\u063A\u0641-\u064A\u0671-\u06D3]+$")
DIACRITICS = re.compile(r"[\u0610-\u061A\u064B-\u065F\u0670\u0640]")


def fold(word):
    """Spelling variants compare equal: no diacritics, one alef, ة → ه, ى → ي."""
    word = DIACRITICS.sub("", word)
    return word.translate(str.maketrans("أإآٱىة", "اااايه"))


def folded(words):
    return {fold(w) for w in words.split()}


GIVEN_NAMES = folded("""
محمد أحمد محمود مصطفى علي عمر عثمان خالد حسن حسين حسام يوسف إبراهيم إسماعيل إسحاق يعقوب
موسى عيسى داود سليمان سليم سالم سعيد سعد سعود فهد فيصل فارس فادي فراس فؤاد فريد كريم كمال
جمال جلال جميل جابر جاسم جواد حمد حمدي حمزة حامد حازم حاتم حارث حبيب حسني هاني هشام هيثم
وليد وائل وسيم وجيه ياسر ياسين يحيى يزن يونس زياد زكريا زيد زين زهير ماجد مازن مالك مأمون
مجدي مراد مروان مصعب معاذ منصور منير مهدي مهند موفق نبيل نادر ناصر نايف نزار نصر نضال نعمان
نوح نواف هادي همام أسامة أنس أنور أمجد أيمن أيوب أكرم أشرف إياد إيهاب باسل باسم بدر بسام بشار
بشير بكر بلال تامر توفيق ثامر رامي رائد راشد رشيد رضا رياض ربيع رفيق رمزي سامي سامر سلطان
سلمان سمير سهيل شادي شريف شاكر صالح صابر صادق صلاح صهيب ضياء طارق طلال طه عادل عاصم عامر
عدنان عزيز عصام علاء عماد عمار عمرو عوض غازي غسان قاسم قيس لؤي لطفي ماهر مؤمن مرتضى معتز
مختار مدحت نجيب نديم نعيم هلال وحيد وديع وسام تركي بندر مشعل متعب نهار عبيد خليل خليفة جعفر
فاطمة عائشة خديجة زينب مريم ليلى سارة نور هند هدى هالة هبة رنا رانيا ريم رهف رغد رزان روان
ربى رقية سلمى سميرة سعاد سناء سهى سوسن شيماء صفاء ضحى عبير علا غادة غدير فرح فدوى لبنى لمى
لينا لانا ليان مها منى مي ميس ميساء ميار نادية نجلاء نجوى نسرين نهى نوال هيفاء وفاء ولاء
ياسمين يارا أسماء أميرة آمنة إيمان آلاء بسمة بشرى تسنيم جميلة جنى حلا حنان خلود دعاء دينا
رحاب رشا رحمة زهرة سحر سمر سهام شذى عفاف فاتن فريدة كوثر لجين ماجدة مروة منار نهلة نيرمين
هناء هيا وداد إسراء آية جود ملك رؤى سجى
""")
# Titles before a name; dropped like "Prof." and "Dr." in Latin script.
HONORIFICS = folded("""
د. د أ.د. أ.د ا.د. أ. م. دكتور دكتورة الدكتور الدكتورة أستاذ أستاذة الأستاذ الأستاذة
بروفيسور بروفيسورة البروفيسور البروفيسورة المهندس المهندسة مهندس مهندسة الشيخ السيد السيدة
""")
# Words that make a heading a label, a topic or an institution, not a full name.
GENERIC_WORDS = folded("""
أستاذ أستاذة الأستاذ دكتور الدكتور مهندس خبير الخبير باحث الباحث مدير رئيس عضو أعضاء محاضر
متحدث جامعي جامعة الجامعة كلية الكلية قسم القسم معهد المعهد مركز المركز هيئة التدريس
الأكاديمي الكادر علم علوم البيانات الذكاء الاصطناعي تعلم الآلة السيرة الذاتية سيرة قالب
نموذج فريق فريقنا ملف شخصي برنامج دورة مقال أخبار وظيفة وظائف التقنية تقنية عام صلى عليه
وسلم رضي عنه عنها رحمه
""")


def arabic_name(value):
    """The name without titles, or None when the phrase is not shaped like a person's name."""
    words = value.split()
    while words and fold(words[0]) in HONORIFICS:
        words.pop(0)
    if not 2 <= len(words) <= 5 or not all(ARABIC_WORD.match(fold(w)) for w in words):
        return None
    if any(fold(w) in GENERIC_WORDS for w in words):
        return None
    first = fold(words[0])
    if first not in GIVEN_NAMES and not first.startswith("عبد"):
        return None
    return " ".join(words)

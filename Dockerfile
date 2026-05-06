FROM python:3.10-slim

WORKDIR /app

# السطر ده هو السر: بيخلي مخرجات البايثون تظهر في اللوج فوراً
ENV PYTHONUNBUFFERED=1

RUN apt-get update && apt-get install -y \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .

RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# إنشاء ملفات الداتا عشان الكود ميعملش Error وهو بيبدأ
RUN touch vbv_codes.txt vbv_users.txt blocked_bins.txt bot_settings.txt registered_users.txt paypal_accounts.txt

# تشغيل البوت باستخدام العلم -u للتأكيد على عدم التخزين المؤقت
CMD ["python", "-u", "3ds.py"]

# Tekno Pusula 🧭

**Tam otomatik, haber doğrulamalı, ücretsiz sosyal medya post sistemi.**

Bu sistem, GitHub Actions üzerinde **tamamen ücretsiz** çalışır. Bilgisayarınızın
açık olmasına gerek yoktur. Günde **5 kez** teknoloji / yapay zeka içeriği üretir:

1. Haberi güvenilir kaynaklardan toplar (RSS)
2. **Çok aşamalı doğrulama** yapar — doğrulanamayan haber **asla yayınlanmaz**
3. 6 slaytlık görsel üretir (1080×1350 + TikTok için 1080×1920)
4. Platforma özel açıklamalar yazar
5. 6 platformda paylaşır (Instagram, TikTok, X, Facebook, LinkedIn, Threads)
6. Her şeyi repoda arşivler (kanıtlar, raporlar, istatistikler)

---

## 📋 İçindekiler

1. [Repoyu oluşturma](#1-repoyu-oluşturma)
2. [GitHub ayarları](#2-github-ayarları)
3. [Secrets tanımlama](#3-secrets-tanımlama)
4. [Buffer profil ID'lerini bulma](#4-buffer-profil-idlerini-bulma)
5. [İlk test (dry run)](#5-ilk-test-dry-run)
6. [Canlıya alma](#6-canlıya-alma)
7. [Sorun giderme](#7-sorun-giderme)
8. [Bilinen kısıtlar](#8-bilinen-kısıtlar)

---

## 1. Repoyu oluşturma

1. GitHub'da **yeni bir depo** oluşturun.
   - ⚠️ Depo **PUBLIC** olmalı (GitHub Actions'ın ücretsiz çalışması için zorunlu).
   - İsim önerisi: `tekno-pusula`
2. Bu klasördeki tüm dosyaları o depoya yükleyin.

Yerel bilgisayarınızda git varsa:

```powershell
cd tekno-pusula
git init
git add .
git commit -m "Tekno Pusula: ilk kurulum"
git branch -M main
git remote add origin https://github.com/KULLANICI_ADINIZ/tekno-pusula.git
git push -u origin main
```

## 2. GitHub ayarları

Depo sayfasında:

1. **Settings → Actions → General**
2. **Workflow permissions** bölümü:
   - ✅ **"Read and write permissions"** seçeneğini işaretleyin
   - ✅ "Allow GitHub Actions to create and approve pull requests" işaretli olabilir
3. **Save** butonuna basın.

> Bu ayar olmadan workflow commit atamaz ve paylaşım durumlarını kaydedemez.

## 3. Secrets tanımlama

**Settings → Secrets and variables → Actions → "New repository secret"** ile
aşağıdaki secret'ları ekleyin. **Hiçbir anahtar koda yazılmaz, loglanmaz.**

| Secret | Nereden alınır | Zorunlu mu? |
|--------|----------------|-------------|
| `GEMINI_API_KEY` | [Google AI Studio](https://aistudio.google.com/apikey) — "Create API key" | ✅ Evet |
| `PEXELS_API_KEY` | [Pexels API](https://www.pexels.com/api/) — ücretsiz kayıt | ✅ Evet |
| `BUFFER_ACCESS_TOKEN_A` | Buffer → [Settings → API](https://publish.buffer.com/settings/api) | ✅ Evet |
| `BUFFER_ACCESS_TOKEN_B` | Aynı sayfadan (ikinci anahtar) veya aynı anahtar | ✅ Evet |
| `BUFFER_PROFILE_INSTAGRAM` | [Bölüm 4](#4-buffer-profil-idlerini-bulma) | ✅ Evet |
| `BUFFER_PROFILE_TIKTOK` | [Bölüm 4](#4-buffer-profil-idlerini-bulma) | ✅ Evet |
| `BUFFER_PROFILE_X` | [Bölüm 4](#4-buffer-profil-idlerini-bulma) | ✅ Evet |
| `BUFFER_PROFILE_FACEBOOK` | [Bölüm 4](#4-buffer-profil-idlerini-bulma) | ✅ Evet |
| `BUFFER_PROFILE_LINKEDIN` | [Bölüm 4](#4-buffer-profil-idlerini-bulma) | ✅ Evet |
| `THREADS_ACCESS_TOKEN` | [Meta for Developers](https://developers.facebook.com/docs/threads/) — Threads API | ✅ Evet (Threads için) |
| `THREADS_USER_ID` | Aynı yerden (Threads kullanıcı ID) | ✅ Evet (Threads için) |
| `GH_PAT` | [GitHub → Settings → Developer settings → Personal access tokens](https://github.com/settings/tokens) — `repo` + `secrets` izinli | ✅ Evet (Threads token yenileme için) |

### Secret detayları

- **GEMINI_API_KEY:** Ücretsiz katman yeterlidir. Model adı gerekirse
  **Settings → Actions → Variables** kısmından `GEMINI_MODEL` değişkenini
  ekleyin (varsayılan: `gemini-2.5-flash`).
- **BUFFER_ACCESS_TOKEN_A / B:** Buffer'ın yeni GraphQL API'si tek bir API anahtarı
  kullanır. İki hesabınız varsa iki ayrı anahtar; tek hesap için aynı anahtarı
  iki yere de yazabilirsiniz.
- **GH_PAT:** Threads token yenileme (60 günde bir) repo secret'ını güncellemek
  için gerekir. `GITHUB_TOKEN` secret yazma iznine sahip **değildir**.
  En az `repo` ve `secrets` izinlerini verin.

## 4. Buffer profil ID'lerini bulma

1. GitHub'da **Actions** sekmesine gidin.
2. **"tools"** workflow'unu seçin.
3. **"Run workflow"** butonuna basın.
4. `tool` seçeneğinden **"list_buffer_profiles"** seçin → **Run workflow**.
5. Birkaç dakika sonra işin log'larını açın. Tüm kanallarınız listelenir:

```
- Tekno Pusula (instagram, hesap A)
  channel_id: 1234567890abcdef
  secret adı: BUFFER_PROFILE_INSTAGRAM
```

6. Her `channel_id` değerini ilgili secret olarak ekleyin (Bölüm 3).

## 5. İlk test (dry run)

> **Önemli:** İlk testi `dry_run=true` ile yapın. Bu mod her şeyi üretir ve
> commit eder ama **hiçbir platforma paylaşmaz**.

1. **Actions → "post" → Run workflow**
2. `dry_run` = ✅ işaretleyin
3. **Run workflow** deyin.
4. İş bittiğinde depodaki `output/YYYY-MM-DD/...` klasörünü kontrol edin:

```
output/2026-10-15/01-0900-ornek-baslik/
├── slides/            slide-1.png ... slide-6.png   (1080×1350)
├── slides_9x16/       slide-1.png ... slide-6.png   (1080×1920, TikTok)
├── images/            indirilen görseller
├── sources/           kaynak metin alıntıları (.txt)
├── content.json       slayt metinleri
├── captions.json      platform açıklamaları
├── captions.md        okunabilir açıklamalar
├── verification.md    doğrulama raporu (iddia-kanıt eşleşmesi)
├── evidence.json      makine okunur doğrulama verisi
├── credits.json       görsel lisans/kaynakları
├── status.json        platform paylaşım durumları
└── meta.json          slot, tip, model, süre vb.
```

**Kontrol edin:**
- Slaytlarda taşmış/kesik yazı var mı? (yoksa iyi)
- Türkçe karakterler doğru mu? ("İÇİN" yazmalı, "IÇIN" **yazmamalı**)
- `verification.md` içinde her iddia ve kanıtı görünüyor mu?
- `captions.md` içindeki açıklamalar mantıklı mı?

### Yerelde test (opsiyonel)

Python 3.12+ kuruluysa:

```powershell
pip install -r requirements.txt
python -m playwright install chromium
python -m app.render.sample          # örnek post üretir (Gemini gerektirmez)
python -m app.tools.preview output\_sample
python -m pytest tests/ -v           # testler
```

## 6. Canlıya alma

1. Dry run sonucundan memnun kaldıysanız **Actions → "post" → Run workflow**
2. `dry_run` **işaretli OLMAMALI** → **Run workflow**
3. İlk paylaşım 5-10 dakika sürebilir.
4. `status.json` dosyasında her platformun durumu görünür:
   - `published` ✅ paylaşılıldı
   - `failed` ❌ hata (aynı zamanda GitHub Issue açılır)

Otomatik zamanlama zaten tanımlıdır:
**Her gün 09:00, 12:00, 15:00, 18:00, 21:00** (Türkiye saati).
18:00 slotu eğitim/bilgi postudur; diğerleri haberdir.

## 7. Sorun giderme

| Belirti | Çözüm |
|---------|-------|
| Workflow "Resource not accessible by integration" hatası | Bölüm 2'deki "Read and write permissions" ayarını yapın |
| `GEMINI_API_KEY tanımlı değil` | Secret adını tam olarak `GEMINI_API_KEY` yapın |
| `Buffer API anahtarı geçersiz (401)` | Buffer → Settings → API'den yeni anahtar alın, secret'ı güncelleyin |
| `THREADS_ACCESS_TOKEN / THREADS_USER_ID tanımlı değil` | İki secret'ı da ekleyin; Threads kullanmıyorsanız boş bırakabilirsiniz (loglarda uyarı çıkar) |
| `Slot atlandı` mesajı | O saatte doğrulanabilir haber bulunamadı — normal, bir sonraki slotta devam eder |
| Slaytlarda taşmış yazı | Nadirdir; sistem otomatik küçültür. Tekrarlarsa `content.json`'daki metinleri kısaltıp tekrar çalıştırın |
| Paylaşım `failed` | Depoda otomatik açılan issue'ya bakın. Çözüldüğünde sonraki başarılı paylaşım issue'yu otomatik kapatır |
| Cron hiç çalışmıyor | GitHub, 60 gün hareketsiz depolarda cron'u kapatır. Bu sistem her gün commit attığı için kapanmaz; yine de Actions sekmesinden manuel çalıştırabilirsiniz |

### ⏱️ Zamanlama gecikmelerini tamamen önleme (external cron — önerilen)

GitHub Actions `schedule` yoğunlukta **saatlerce gecikebilir** (cron UTC'de
planlanır ama GitHub koşuları erteleyip atlayabilir). Sistem bunu bir sonraki
çalışmada telafi eder (catch-up), yani postlar kaybolmaz; sadece geç paylaşılır.
Tam dakikasında paylaşım için harici bir tetikleyici kullanın:

1. GitHub'da **Settings → Developer settings → Personal access tokens →
   Fine-grained token** oluşturun.
   - Repository access: yalnızca bu depo
   - Permissions: `Actions` → **Read and write**, `Contents` → **Read and write**
2. Ücretsiz bir cron servisine kaydolun: [cron-job.org](https://cron-job.org),
   [EasyCron](https://www.easycron.com) veya benzeri.
3. Şu ayarlarla bir görev oluşturun:
   - **URL:** `https://api.github.com/repos/KULLANICI_ADINIZ/tekno-pusula/actions/workflows/publish.yml/dispatches`
   - **Method:** `POST`
   - **Headers:** `Authorization: Bearer <TOKEN>` ve `Accept: application/vnd.github+json`
   - **Body:** `{"ref":"main","inputs":{"dry_run":"false","force_type":"auto"}}`
   - **Sıklık:** her 5 dakikada bir
4. Görevin çalıştığını [cron-job.org](https://cron-job.org) loglarından doğrulayın.

Bu kurulum GitHub'ın kendi cron'unu tamamen devre dışı bırakır; kontrol sizde olur.
`post` workflow'u idempotent olduğu için sık tetiklemek zararsızdır.
| Threads "token süresi dolmuş" | **Actions → tools → refresh_threads_token** ile yenileyin (`force` işaretleyin) |

## 8. Bilinen kısıtlar

- **Reuters ve Anthropic'in halka açık RSS beslemesi yoktur** (2026-10 kontrolü:
  Reuters 401/engelli, Anthropic 404). Bu iki kaynak doğrulama amacıyla
  grounding üzerinden kullanılır; birincil kaynak listesinde yer almaz.
- **Buffer Carousel/TikTok modu:** Buffer API'si çoklu görsel (`assets` listesi)
  destekler; TikTok'a 9:16 varyantı gönderilir. Buffer'ın TikTok'ta tam video
  desteğini sizin hesap ayarlarınız belirler. Görsel karusel her platformda
  Buffer destekliyorsa gönderilir; desteklenmiyorsa ilk görsel kullanılır.
- **X (Twitter) 4 görsel sınırı:** X tek tweette en fazla 4 görsel kabul eder.
  5-6. görseller yanıt tweetine eklenir (thread). Buffer thread desteklemezse
  yalnızca ilk 4 görsel paylaşılır.
- **Threads karakter sayımı:** Threads'te emojiler UTF-8 byte olarak sayılır.
  Kod bu sayımı uygular; 500 karakter sınırı aşılmaz.
- **Ücretsiz API limitleri:** Gemini ücretsiz katmanında dakikada sınırlı istek
  vardır. Sistem rate limiter + yedek model kullanır. Günde 5 post için yeterlidir;
  aşarsa `GEMINI_FALLBACK_MODEL` devreye girer.
- **Buffer rate limit:** Ücretsiz planda 15 dakikada 100, günde 250 istek.
  Sistem bunu aşmaz (bir post ~5-8 API çağrısı yapar).
- **60 günlük Threads token:** Long-lived token 60 gün geçerlidir. Sistem 40.
  günde otomatik yeniler (GH_PAT gerekli). GitHub cron kapansa bile token
  yenileme manuel yapılabilir.

---

## 📁 Proje yapısı

```
tekno-pusula/
├── .github/workflows/
│   ├── post.yml            ana zamanlanmış iş
│   ├── cleanup.yml         haftalık temizlik (eski görseller)
│   ├── tools.yml           manuel yardımcılar (Buffer profil, token yenileme)
│   └── test.yml            push'ta testler
├── app/
│   ├── main.py             orkestrasyon (CLI)
│   ├── config.py           pydantic-settings + YAML
│   ├── collect/            RSS, makale metni, tarih/slot
│   ├── select/             puanlama, tekrar önleme
│   ├── verify/             iddia çıkarımı, çapraz kaynak, doğrulama, rapor
│   ├── write/              slayt metinleri, platform açıklamaları
│   ├── media/              Wikimedia, Pexels, og:image, logolar
│   ├── render/             HTML şablonları, Playwright render, taşma kontrolü, QA
│   ├── publish/            Buffer (GraphQL), Threads (Graph API), retry
│   ├── store/              history, git işlemleri, GitHub issues
│   ├── llm/                Gemini istemcisi + prompt'lar
│   └── tools/              yardımcı araçlar
├── config/                 sources.yaml, platforms.yaml, schedule.yaml, brand.yaml
├── data/                   history.json, token_state.json
├── assets/fonts/           Google Fonts (yerel, indirilir)
├── tests/                  pytest testleri
└── output/                 üretilen postlar (commit edilir)
```

## 🛡️ Güvenlik

- Hiçbir token/anahtar koda, loga veya commit'e yazılmaz. Hepsi GitHub Secrets'tan.
- Loglarda secret değerleri maskelenir (`mask_secret`).
- Görsel alıntıları kodla doğrulanır: kaynak metinde geçmeyen alıntı reddedilir.
- `contradicted` tek bir iddia bile varsa haber yayınlanmaz.
- 2 bağımsız kaynak doğrulaması olmadan haber yayınlanmaz.
# Tekno Pusula 🧭

Kaynakları kontrol edilen Türkçe teknoloji / yapay zekâ içeriği üretir; altı slayt ve uygun gerçek video varsa Reels/TikTok videosu hazırlar. GitHub Actions üzerinde çalışır.

## İçerik politikası

- Öncelik: anlamlı AI gelişmeleri, yazılım, siber güvenlik, çipler, robotik ve uzay/bilim.
- Aksesuar, indirim, küçük ürün varyantı, rutin ürün tanıtımı, inceleme özeti, dedikodu, siyaset/magazin ve kripto fiyatları haber seçiminin dışında tutulur.
- Adaylar tek bir toplu editör değerlendirmesinden geçer. Önemi 7/10 altında veya somut okur faydası olmayan haber seçilmez. Karar ve gerekçesi `meta.json` içinde saklanır.
- Aynı şirket günde en fazla 1, aynı konu en fazla 2, tüketici elektroniği en fazla 1 paylaşımda ana konu olur.
- Şirket/konu bilgisi tekrar kontrolünden **önce** hazırlanır. Olay kimliği ve geçmiş başlıklar, farklı kaynakların aynı haberi yeniden paylaşmasını azaltır.
- Haber metni iki tur kontrol edilir. Alıntı, belirtilen kaynak URL'sinin gerçek metninde bulunmalıdır. Ana iddia için en az iki ayrı kaynak alan adından kanıt gerekir.
- Doğrulanmış haber bulunmazsa slot atlanır; boşluğu doldurmak için rastgele eğitim içeriği üretilmez. Atlanan slot, aynı gün tekrar tekrar denenmez.
- 18:00 eğitim slotunda haberin uygulanabilir bir kavramı öğretmeye uygunluğu da değerlendirilir.
- Son slayt metni sınır ve rakam kontrollerini, görseller de DOM/vision kalite kontrolünü geçmeden paylaşım başlamaz.

Bu kontroller otomatik doğrulamadır; hatasız editörlük garantisi değildir.

## Zamanlama

Türkiye saatiyle 09:00, 12:00, 15:00, 18:00 (eğitim) ve 21:00 hedeflenir. Bunlar üst sınırdır; içerik kalitesi için beşinin de dolması zorlanmaz.

GitHub cron her 15 dakikada kontrol eder. İstenirse mevcut harici tetikleyici aynı workflow'u daha sık çağırabilir. `cancel-in-progress: false` sayesinde yeni tetik, devam eden üretimi iptal etmez. Önizlemeler ayrı concurrency grubundadır.

Bir çalışmada yalnızca tek güncel slot işlenir. 90 dakikadan eski kaçırılmış slotlar topluca yayımlanmaz; gelecek slot erken başlatılmaz. Slot yoksa ağır kurulum/üretim atlanır. Son 48 saatin bekleyen gönderileri ayrıca sorgulanır.

Ayarlar: [schedule.yaml](config/schedule.yaml), [publish.yml](.github/workflows/publish.yml).

## AI modelleri ve yedekler

Varsayılan:
- Ana model: `gemini-3.5-flash-lite`.
- Yedek model: `gemini-3.1-flash-lite`.
- İsteğe bağlı ikinci Google anahtarı: `GEMINI_BACKUP_API_KEY`.

Bu modeller yapılandırılmış metin ve görüntü değerlendirmesi için kullanılır. Otomatik havuz ücretli modellere veya görüntü değerlendiremeyen metin modellerine geçmez. Günlük kotası bitmiş model/anahtar aynı çalışma içinde tekrar tekrar çağrılmaz. Dakikalık limitte sınırlı bekleme uygulanır. Kullanılan modeller ve başarılı çağrı sayıları `meta.json → model_usage` içinde görülebilir.

**Google kotayı anahtar değil proje bazında uygular.** Aynı projeye ait iki anahtar bağımsız kapasite sağlamaz. Yedek, kendi kullanım şartları ve kotası olan yetkili bir projeye ait olmalıdır. Anahtarlar sohbete/koda yazılmaz.

İsteğe bağlı ayrı metin sağlayıcısı:

| GitHub ayarı | Tür | Varsayılan / amaç |
|---|---|---|
| `TEXT_FALLBACK_API_KEY` | Secret | Sağlayıcının kendi API anahtarı |
| `TEXT_FALLBACK_BASE_URL` | Variable | `https://api.groq.com/openai/v1` |
| `TEXT_FALLBACK_MODEL` | Variable | `llama-3.3-70b-versatile` |

Google metin isteği başarısız olursa bu sağlayıcı denenir. JSON şeması yine doğrulanır. Bu yedek, görüntü veya Google Search değerlendirmesini taklit etmez; görsel kontrolü yapılamazsa kalite kapısı kapanır. Hesabın ücretsiz planını ve güncel kotalarını sağlayıcının panelinden kontrol et.

[FreeLLMAPI](https://github.com/tashfeenahmed/freellmapi) ve [OmniRoute](https://github.com/diegosouzapw/OmniRoute), sağlayıcıları birleştiren yönlendiricilerdir; kendiliğinden sınırsız ücretsiz model sağlamaz. FreeLLMAPI kendisini kişisel deneme kullanımı için tanımlar. Bu proje ek bir yönlendirici sunucusuna bağlı değildir. Kendi kurduğun ve kullanmaya yetkili olduğun bir /v1 endpoint'i isteğe bağlı metin yedeğine bağlanabilir.

Google Search grounding varsayılan kapalıdır: güncel Gemini 3 ücretsiz API katmanında kullanılabilir değildir. Çapraz kontrol RSS kaynaklarıyla yapılır. Ücretli araç kullanımını bilerek açmak istersen `GEMINI_ENABLE_GROUNDING=true` kullan.

Güncel sağlayıcı belgeleri:
- [Google modelleri](https://ai.google.dev/gemini-api/docs/models)
- [Google fiyatlandırması](https://ai.google.dev/gemini-api/docs/pricing)
- [Google kota kuralları](https://ai.google.dev/gemini-api/docs/rate-limits)
- [Groq modelleri](https://console.groq.com/docs/models), [Groq kotaları](https://console.groq.com/docs/rate-limits)

Ücretsiz kotalar değişebilir; bu proje sabit bir günlük kapasite veya sınırsız ücretsiz kullanım vaat etmez.

## Video

- Öncelik haberin kendi videosu; ardından Wikimedia, Pexels, Pixabay ve NASA.
- En fazla dört farklı video indirme adayı denenir. İndirilen gerçek dosyadan üç kare çıkarılır ve görüntüler birlikte değerlendirilir. Dosya adı/thumbnail tek başına yeterli değildir.
- Çok kısa, düşük çözünürlüklü veya alakasız video reddedilir. Stok/arşiv görüntüsü videoda “Temsili görüntü” olarak işaretlenir.
- 8–26 saniyelik 1080×1920 MP4: kısa giriş, sırayla gösterilen üç somut bilgi, kaynak ve ilerleme göstergesi. Kartların gerçek `card_title/card_body` alanları kullanılır.
- Kaynak görüntünün konusu kırpılarak kaybedilmez; arka planda bulanık dolgu kullanılır. Yazılar sağdaki düğmelerden ve alttaki açıklama alanından uzak tutulur.
- Orijinal ses varsa korunup seviyesi dengelenir; yoksa uygun lisanslı müzik aranır. Video çözünürlüğü/süresi encode sonrası tekrar ölçülür.
- Uygun gerçek video yoksa karusel gönderilir. Slayt yakınlaştırması video diye paylaşılmaz.

## Platformlar ve durum takibi

Instagram, TikTok, X, Facebook, LinkedIn: Buffer GraphQL API. Threads: Threads Graph API.

`status.json` durumları:
- `pending`: Henüz gönderilmedi.
- `submitted`: İstek gönderildi veya Buffer kabul etti; yayına çıktığı henüz doğrulanmadı.
- `published`: Buffer `sent` döndürdü veya Threads yayın kimliği alındı.
- `failed`: Gönderim reddedildi ya da Buffer hata bildirdi.

Buffer ID'si bulunan gönderi tekrar oluşturulmaz; var olan ID sorgulanır. Sonucu belirsiz, ID'siz isteğin yeniden gönderimi de otomatik yapılmaz. Her platform isteğinden önce ve sonra durum günlüğü kaydedilir. Yarım kalan hazırlanmış içerik sonraki çalışmada sürdürülebilir. Medya GitHub'a yüklenememişse veya herkese açık URL'leri erişilemiyorsa paylaşım başlamaz.

Buffer'da `sent` görünmesine rağmen platformda yayın yoksa hesabın otomatik yayın / bildirimle yayın ayarlarını da kontrol et. [Buffer açıklaması](https://support.buffer.com/articles/scheduling-instagram-posts-reels-stories-and-notifications-3XA98S9Q5p).

## GitHub kurulumu

Python 3.12 kullanılır. Depo public ise GitHub Actions ve raw medya URL'leri kullanılabilir. Actions → General → Workflow permissions altında içerik yazma izni gerekir.

Settings → Secrets and variables → Actions:

| Secret | Amaç |
|---|---|
| `GEMINI_API_KEY` | Ana Google API anahtarı |
| `GEMINI_BACKUP_API_KEY` | İsteğe bağlı Google yedeği |
| `PEXELS_API_KEY` | Pexels görsel/video |
| `PIXABAY_API_KEY`, `NASA_API_KEY` | İsteğe bağlı video kaynakları |
| `BUFFER_ACCESS_TOKEN_A`, `BUFFER_ACCESS_TOKEN_B` | Buffer hesapları |
| `BUFFER_PROFILE_INSTAGRAM`, `BUFFER_PROFILE_TIKTOK`, `BUFFER_PROFILE_X`, `BUFFER_PROFILE_FACEBOOK`, `BUFFER_PROFILE_LINKEDIN` | Kanallar |
| `THREADS_ACCESS_TOKEN`, `THREADS_USER_ID` | Threads |
| `GH_PAT` | İsteğe bağlı: Threads token'ını repo secret'ında yenileme |
| `TEXT_FALLBACK_API_KEY` | İsteğe bağlı metin sağlayıcısı |

A/B eşleşmesi `config/platforms.yaml` içindedir. `tools → list_buffer_profiles` kanalları listeler. `tools → refresh_threads_token` token'ı yeniler. `GH_PAT` yoksa otomatik secret yenileme kullanılamaz; Threads token'ını süresi dolmadan panelden güncelle.

Model adları `GEMINI_MODEL` / `GEMINI_FALLBACK_MODEL` Variables ile değiştirilebilir.

## Önizleme

Actions → **post** → Run workflow → `dry_run=true`.

Bu mod içerik/görsel/video üretir; Buffer/Threads'e göndermez, Git'e commit/push yapmaz ve yayın geçmişini değiştirmez. Sonuçlar workflow'un **post-preview-…** artifact'ında 7 gün saklanır. Hata durumunda o ana kadar üretilmiş güncel tarih klasörü de artifact'a alınır.

Canlı çalışma için `dry_run=false`. Üretim başlamadan mevcut kanal ve anahtar ayarlarını kontrol et.

## Yerel geliştirme ve test

```sh
python3.12 -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
python -m playwright install --with-deps chromium
# Sistem paket yöneticisiyle FFmpeg / ffprobe ve Noto fontlarını kur.
python -m pytest tests/ -q
python scripts/smoke_render.py
```

Smoke testi gerçek Chromium ile 12 PNG ve FFmpeg ile H.264/AAC MP4 üretir. API anahtarı veya sosyal medya bağlantısı gerektirmez. Çıktısı `output/_sample/` içindedir ve Git'e dahil edilmez. CI aynı smoke testini çalıştırır.

Playwright ve Google SDK sürümleri sabitlenmiştir. Workflow, browser cache bulunsa bile kurulu Playwright'ın gerektirdiği Chromium sürümünün varlığını doğrular.

## Dosyalar

- `app/main.py`: ana akış.
- `app/select/`: editör filtresi, puanlama, tekrar ve çeşitlilik.
- `app/verify/`: kaynak ve iddia kontrolü.
- `app/llm/`: model/anahtar failover.
- `app/media/`, `app/render/`: medya, slayt ve video.
- `app/publish/`: API istemcileri, durum günlüğü ve kurtarma.
- `config/`: kaynak, marka, takvim ve platform ayarları.
- `data/history.json`: yayın geçmişi; `data/skipped_slots.json`: atlanan slotlar.
- `output/TARİH/POST/`: içerik, açıklamalar, doğrulama, lisanslar, medya, metadata ve platform durumları.

Haftalık cleanup 30 günden eski indirilen `images/` klasörlerini temizler. Slaytlar ve kanıtlar kalır.

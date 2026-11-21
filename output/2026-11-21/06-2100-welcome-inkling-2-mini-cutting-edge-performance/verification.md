# Doğrulama Raporu

**Haber:** Welcome Inkling 2 Mini, Cutting-edge Performance for your Local Setup
**Canonical URL:** https://huggingface.co/blog/inkling2mini
**Kaynaklar:** Hugging Face Blog
**Kontrol zamanı:** 2026-11-21T21:03:11+03:00
**Sonuç:** ✅ YAYINLANABİLİR

---

## İddia Bazlı Sonuçlar

### 1. Inkling 2 Mini, ~26B fiziksel toplam ve token başına 3B aktif parametreye sahip çok modlu bir Karışım-Uzman (Mixture-of-Experts) modelidir.
- **Karar:** ✅ `supported`
- **Kanıtlar:**
  - [https://huggingface.co/blog/inkling2mini](https://huggingface.co/blog/inkling2mini)
    > It’s a multimodal Mixture-of-Experts with ~26B physical total and 3B active parameters per token.

### 2. Inkling 2 Mini, 1M token bağlam boyutunu destekler ve hem görsel hem de metin girdilerini kabul eder.
- **Karar:** ✅ `supported`
- **Kanıtlar:**
  - [https://huggingface.co/blog/inkling2mini](https://huggingface.co/blog/inkling2mini)
    > It supports a 1M-token context size, accepts images and text inputs.

### 3. Inkling 2 Mini, 24 kod çözücü katmanına sahiptir ancak ortadaki 12 katman döngü içinde üç kez çalışır.
- **Karar:** ✅ `supported`
- **Kanıtlar:**
  - [https://huggingface.co/blog/inkling2mini](https://huggingface.co/blog/inkling2mini)
    > Inkling 2 Mini is a mixture-of-experts model with 24 decoder layers, but the 12 middle layers run three times in a loop.

### 4. Inkling 2 Mini, Artificial Analysis Intelligence Index v5 (AAv5) içerisinde kendi sınıfında son teknoloji ürünüdür.
- **Karar:** ✅ `supported`
- **Kanıtlar:**
  - [https://huggingface.co/blog/inkling2mini](https://huggingface.co/blog/inkling2mini)
    > Inkling 2 Mini is state-of-the-art in its class in the Artificial Analysis Intelligence Index v5 (AAv5)
  - [https://huggingface.co/blog/inkling2mini](https://huggingface.co/blog/inkling2mini)
    > Inkling 2 Mini is state-of-the-art in its class in the Artificial Analysis Intelligence Index v5 (AAv5), as well as across many benchmarks in various categories.

### 5. Inkling 2 Mini, Gemma 4 31B, Muse Glimmer, Qwen3.8-27B ve Nemotron 3.5 Super VL ile karşılaştırıldığında 48 benchmark testinin 32'sinde liderdir.
- **Karar:** ✅ `supported`
- **Kanıtlar:**
  - [https://huggingface.co/blog/inkling2mini](https://huggingface.co/blog/inkling2mini)
    > Compared with Gemma 4 31B, Muse Glimmer, Qwen3.8-27B, and Nemotron 3.5 Super VL, Inkling 2 Mini leads in 32 benchmarks out of 48.

### 6. Thinking Machines Lab, modeli NVFP4 ve MXFP8 uzman ağırlıklarıyla karışık hassasiyet formatında sunmaktadır.
- **Karar:** ✅ `supported`
- **Kanıtlar:**
  - [https://huggingface.co/blog/inkling2mini](https://huggingface.co/blog/inkling2mini)
    > Thinking Machines Lab ships the model in a mixed-precision format, with NVFP4 and MXFP8 expert weights.

### 7. Inkling 2 Mini modeli için GGUF 4-bit (IQ4_NL) ve 8-bit (Q8_0) kuantizasyonları sağlanmaktadır.
- **Karar:** ⚠️ `not_found`
- **Kanıt:** yok

### 8. SGLang, veri merkezi donanımında üretim dağıtımları için Inkling 2 Mini modeline sıfırıncı gün (day-zero) çıkarım desteği sağlar.
- **Karar:** ✅ `supported`
- **Kanıtlar:**
  - [https://huggingface.co/blog/inkling2mini](https://huggingface.co/blog/inkling2mini)
    > SGLang also provides day-zero inference support for production deployments on datacenter hardware.

---

## İki Tur Karşılaştırması

| İddia | 1. Tur | 2. Tur | Nihai |
|-------|--------|--------|-------|
| Inkling 2 Mini, ~26B fiziksel toplam ve token başına 3B akti | supported | supported | supported |
| Inkling 2 Mini, 1M token bağlam boyutunu destekler ve hem gö | supported | supported | supported |
| Inkling 2 Mini, 24 kod çözücü katmanına sahiptir ancak ortad | supported | supported | supported |
| Inkling 2 Mini, Artificial Analysis Intelligence Index v5 (A | supported | supported | supported |
| Inkling 2 Mini, Gemma 4 31B, Muse Glimmer, Qwen3.8-27B ve Ne | supported | supported | supported |
| Thinking Machines Lab, modeli NVFP4 ve MXFP8 uzman ağırlıkla | supported | supported | supported |
| Inkling 2 Mini modeli için GGUF 4-bit (IQ4_NL) ve 8-bit (Q8_ | not_found | not_found | not_found |
| SGLang, veri merkezi donanımında üretim dağıtımları için Ink | supported | supported | supported |

## Kaynak Metinleri

- `sources/source-1.txt` — https://huggingface.co/blog/inkling2mini
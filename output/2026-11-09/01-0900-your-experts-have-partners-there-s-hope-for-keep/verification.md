# Doğrulama Raporu

**Haber:** Your Experts Have Partners. There's HOPE for Keeping Them Together
**Canonical URL:** https://huggingface.co/blog/amazon/higher-order-pruning-experts
**Kaynaklar:** Hugging Face Blog, Engadget, Wired, TechCrunch
**Kontrol zamanı:** 2026-11-09T15:48:08+03:00
**Sonuç:** ✅ YAYINLANABİLİR

---

## İddia Bazlı Sonuçlar

### 1. Qwen3.5-122B modelinde her birinde 256 uzman bulunan 48 adet MoE katmanı mevcuttur.
- **Karar:** ✅ `supported`
- **Kanıtlar:**
  - [https://huggingface.co/blog/amazon/higher-order-pruning-experts](https://huggingface.co/blog/amazon/higher-order-pruning-experts)
    > For example, Qwen3.5-122B has 256 experts in each of its 48 MoE layers

### 2. Qwen3.5-122B modelinin yaklaşık 250 GB'lık parametre belleğinin %95'i uzman MLP'leri tarafından kaplanmaktadır.
- **Karar:** ✅ `supported`
- **Kanıtlar:**
  - [https://huggingface.co/blog/amazon/higher-order-pruning-experts](https://huggingface.co/blog/amazon/higher-order-pruning-experts)
    > and 95% of its ~250 GB parameter memory footprint is taken up entirely by these expert MLPs alone.
  - [https://huggingface.co/blog/amazon/higher-order-pruning-experts](https://huggingface.co/blog/amazon/higher-order-pruning-experts)
    > For example, Qwen3.5-122B has 256 experts in each of its 48 MoE layers, and 95% of its ~250 GB parameter memory footprint is taken up entirely by these expert MLPs alone.

### 3. HOPE yöntemi, uzmanlar arasındaki ikili etkileşimleri hesaba katan ikinci dereceden bir budama yöntemidir.
- **Karar:** ✅ `supported`
- **Kanıtlar:**
  - [https://huggingface.co/blog/amazon/higher-order-pruning-experts](https://huggingface.co/blog/amazon/higher-order-pruning-experts)
    > Our newest paper derives HOPE (Higher-Order Pruning of Experts), a second-order method that accounts for pairwise expert interactions.

### 4. HOPE yöntemi %50 budama oranında, bir sonraki en iyi budama yöntemine kıyasla agentic kodlama görevlerinde %6,1'e varan performans artışı sağlamaktadır.
- **Karar:** ✅ `supported`
- **Kanıtlar:**
  - [https://huggingface.co/blog/amazon/higher-order-pruning-experts](https://huggingface.co/blog/amazon/higher-order-pruning-experts)
    > At 50% pruning, HOPE achieves the best average rank of any method, with gains of up to +6.1% on agentic coding tasks over the next-best pruning method.

### 5. GLM-4.5-Air modeli, katman başına 128 uzman ve toplam 106 milyar parametreye sahiptir.
- **Karar:** ✅ `supported`
- **Kanıtlar:**
  - [https://huggingface.co/blog/amazon/higher-order-pruning-experts](https://huggingface.co/blog/amazon/higher-order-pruning-experts)
    > Visualization of the interaction matrix F for GLM-4.5-Air (128 experts per layer, 106B parameters total) at three representative layers (early, middle, late).
  - [https://huggingface.co/blog/amazon/higher-order-pruning-experts](https://huggingface.co/blog/amazon/higher-order-pruning-experts)
    > Visualization of the interaction matrix F for GLM-4.5-Air (128 experts per layer, 106B parameters total)

### 6. HOPE yöntemi, Qwen3.5-122B, Qwen3.5-35B ve GLM-4.5-Air olmak üzere üç farklı model üzerinde test edilmiştir.
- **Karar:** ✅ `supported`
- **Kanıtlar:**
  - [https://huggingface.co/blog/amazon/higher-order-pruning-experts](https://huggingface.co/blog/amazon/higher-order-pruning-experts)
    > We evaluated HOPE as an expert pruning method using 3 models (Qwen3.5-122B, Qwen3.5-35B, and GLM-4.5-Air)

### 7. HOPE yöntemi, Evol-CodeAlpaca ve SWE-Bench Verified trajectories olmak üzere iki farklı kalibrasyon veri seti kullanılarak değerlendirilmiştir.
- **Karar:** ✅ `supported`
- **Kanıtlar:**
  - [https://huggingface.co/blog/amazon/higher-order-pruning-experts](https://huggingface.co/blog/amazon/higher-order-pruning-experts)
    > We evaluated HOPE as an expert pruning method using 3 models (Qwen3.5-122B, Qwen3.5-35B, and GLM-4.5-Air), with 2 calibration datasets (Evol-CodeAlpaca and SWE-Bench Verified trajectories).

### 8. Qwen3.5-35B-A3B modelinde %50 budama oranında HOPE yöntemi SWE-Bench Pro üzerinde 42,3 puan alırken, budanmamış model 41,8 puan almıştır.
- **Karar:** ⚠️ `not_found`
- **Kanıt:** yok

---

## İki Tur Karşılaştırması

| İddia | 1. Tur | 2. Tur | Nihai |
|-------|--------|--------|-------|
| Qwen3.5-122B modelinde her birinde 256 uzman bulunan 48 adet | supported | supported | supported |
| Qwen3.5-122B modelinin yaklaşık 250 GB'lık parametre belleği | supported | supported | supported |
| HOPE yöntemi, uzmanlar arasındaki ikili etkileşimleri hesaba | supported | supported | supported |
| HOPE yöntemi %50 budama oranında, bir sonraki en iyi budama  | supported | supported | supported |
| GLM-4.5-Air modeli, katman başına 128 uzman ve toplam 106 mi | supported | supported | supported |
| HOPE yöntemi, Qwen3.5-122B, Qwen3.5-35B ve GLM-4.5-Air olmak | supported | supported | supported |
| HOPE yöntemi, Evol-CodeAlpaca ve SWE-Bench Verified trajecto | supported | supported | supported |
| Qwen3.5-35B-A3B modelinde %50 budama oranında HOPE yöntemi S | not_found | not_found | not_found |

## Kaynak Metinleri

- `sources/source-1.txt` — https://huggingface.co/blog/amazon/higher-order-pruning-experts
- `sources/source-2.txt` — https://www.engadget.com/2309615/safest-laptop-storage-long-term/
- `sources/source-3.txt` — https://www.wired.com/story/how-to-remind-your-boss-about-your-vacation/
- `sources/source-4.txt` — https://techcrunch.com/2026/11/07/parents-want-safer-phones-for-kids-these-companies-are-answering-the-call/
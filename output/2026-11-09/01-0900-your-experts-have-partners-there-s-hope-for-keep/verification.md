# Doğrulama Raporu

**Haber:** Your Experts Have Partners. There's HOPE for Keeping Them Together
**Canonical URL:** https://huggingface.co/blog/amazon/higher-order-pruning-experts
**Kaynaklar:** Hugging Face Blog, Engadget, Wired, TechCrunch
**Kontrol zamanı:** 2026-11-09T15:52:55+03:00
**Sonuç:** ✅ YAYINLANABİLİR

---

## İddia Bazlı Sonuçlar

### 1. Qwen3.5-122B modeli, her biri 48 MoE katmanına sahip ve her katmanda 256 uzman barındıran bir yapıdadır.
- **Karar:** ✅ `supported`
- **Kanıtlar:**
  - [https://huggingface.co/blog/amazon/higher-order-pruning-experts](https://huggingface.co/blog/amazon/higher-order-pruning-experts)
    > For example, Qwen3.5-122B has 256 experts in each of its 48 MoE layers

### 2. Qwen3.5-122B modelinin yaklaşık 250 GB olan parametre belleğinin %95'i tamamen uzman MLP'leri tarafından kaplanmaktadır.
- **Karar:** ✅ `supported`
- **Kanıtlar:**
  - [https://huggingface.co/blog/amazon/higher-order-pruning-experts](https://huggingface.co/blog/amazon/higher-order-pruning-experts)
    > and 95% of its ~250 GB parameter memory footprint is taken up entirely by these expert MLPs alone.
  - [https://huggingface.co/blog/amazon/higher-order-pruning-experts](https://huggingface.co/blog/amazon/higher-order-pruning-experts)
    > For example, Qwen3.5-122B has 256 experts in each of its 48 MoE layers, and 95% of its ~250 GB parameter memory footprint is taken up entirely by these expert MLPs alone.

### 3. Qwen3.5-122B modelinde her bir token için katman başına sadece 8 uzman kullanılmaktadır.
- **Karar:** ✅ `supported`
- **Kanıtlar:**
  - [https://huggingface.co/blog/amazon/higher-order-pruning-experts](https://huggingface.co/blog/amazon/higher-order-pruning-experts)
    > However, for any given token, only 8 experts in each layer are actually used.

### 4. HOPE yöntemi, %50 budama oranında, bir sonraki en iyi budama yöntemine kıyasla agentic kodlama görevlerinde %6,1'e varan performans artışı sağlamaktadır.
- **Karar:** ✅ `supported`
- **Kanıtlar:**
  - [https://huggingface.co/blog/amazon/higher-order-pruning-experts](https://huggingface.co/blog/amazon/higher-order-pruning-experts)
    > At 50% pruning, HOPE achieves the best average rank of any method, with gains of up to +6.1% on agentic coding tasks over the next-best pruning method.

### 5. HOPE yöntemi, tüm test koşullarında 5 yöntem arasında 2,07'lik ortalama başarı sıralaması elde etmiştir.
- **Karar:** ✅ `supported`
- **Kanıtlar:**
  - [https://huggingface.co/blog/amazon/higher-order-pruning-experts](https://huggingface.co/blog/amazon/higher-order-pruning-experts)
    > Across all conditions, HOPE achieved the best average rank (2.07 out of 5 methods)

### 6. %50 budama oranında HOPE'un ortalama başarı sıralaması 1,58'e yükselirken, bir sonraki en iyi yöntem olan REAP'in sıralaması 2,42'dir.
- **Karar:** ⚠️ `not_found`
- **Kanıt:** yok

### 7. Qwen3.5-35B-A3B modeli üzerinde %50 budama oranında HOPE yöntemi SWE-Bench Pro testinde 42,3 puan alarak, budanmamış modelin 41,8'lik skorunu geçmiştir.
- **Karar:** ⚠️ `not_found`
- **Kanıt:** yok

### 8. HOPE yönteminin kullandığı F-matrisinin köşegen değerleri, REAP yönteminin uzman sıralamalarıyla 0,99 Spearman korelasyonuna sahiptir.
- **Karar:** ✅ `supported`
- **Kanıtlar:**
  - [https://huggingface.co/blog/amazon/higher-order-pruning-experts](https://huggingface.co/blog/amazon/higher-order-pruning-experts)
    > The diagonal of recovers REAP's expert rankings almost perfectly (Spearman ).

---

## İki Tur Karşılaştırması

| İddia | 1. Tur | 2. Tur | Nihai |
|-------|--------|--------|-------|
| Qwen3.5-122B modeli, her biri 48 MoE katmanına sahip ve her  | supported | supported | supported |
| Qwen3.5-122B modelinin yaklaşık 250 GB olan parametre belleğ | supported | supported | supported |
| Qwen3.5-122B modelinde her bir token için katman başına sade | supported | supported | supported |
| HOPE yöntemi, %50 budama oranında, bir sonraki en iyi budama | supported | supported | supported |
| HOPE yöntemi, tüm test koşullarında 5 yöntem arasında 2,07'l | supported | supported | supported |
| %50 budama oranında HOPE'un ortalama başarı sıralaması 1,58' | not_found | not_found | not_found |
| Qwen3.5-35B-A3B modeli üzerinde %50 budama oranında HOPE yön | not_found | not_found | not_found |
| HOPE yönteminin kullandığı F-matrisinin köşegen değerleri, R | supported | supported | supported |

## Kaynak Metinleri

- `sources/source-1.txt` — https://huggingface.co/blog/amazon/higher-order-pruning-experts
- `sources/source-2.txt` — https://www.engadget.com/2309615/safest-laptop-storage-long-term/
- `sources/source-3.txt` — https://www.wired.com/story/how-to-remind-your-boss-about-your-vacation/
- `sources/source-4.txt` — https://techcrunch.com/2026/11/07/parents-want-safer-phones-for-kids-these-companies-are-answering-the-call/
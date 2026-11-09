# Doğrulama Raporu

**Haber:** Your Experts Have Partners. There's HOPE for Keeping Them Together
**Canonical URL:** https://huggingface.co/blog/amazon/higher-order-pruning-experts
**Kaynaklar:** Hugging Face Blog, Engadget, Wired, TechCrunch
**Kontrol zamanı:** 2026-11-09T15:37:38+03:00
**Sonuç:** ✅ YAYINLANABİLİR

---

## İddia Bazlı Sonuçlar

### 1. Qwen3.5-122B modeli, 48 MoE katmanının her birinde 256 uzmana sahiptir.
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

### 3. HOPE (Higher-Order Pruning of Experts), uzmanlar arasındaki ikili etkileşimleri hesaba katan ikinci dereceden bir budama yöntemidir.
- **Karar:** ✅ `supported`
- **Kanıtlar:**
  - [https://huggingface.co/blog/amazon/higher-order-pruning-experts](https://huggingface.co/blog/amazon/higher-order-pruning-experts)
    > Our newest paper derives HOPE (Higher-Order Pruning of Experts), a second-order method that accounts for pairwise expert interactions.

### 4. HOPE yöntemi, %50 budama oranında, en iyi ikinci budama yöntemine kıyasla agentic kodlama görevlerinde %6,1'e varan performans artışı sağlamaktadır.
- **Karar:** ✅ `supported`
- **Kanıtlar:**
  - [https://huggingface.co/blog/amazon/higher-order-pruning-experts](https://huggingface.co/blog/amazon/higher-order-pruning-experts)
    > At 50% pruning, HOPE achieves the best average rank of any method, with gains of up to +6.1% on agentic coding tasks over the next-best pruning method.

### 5. HOPE yöntemi, tüm koşullar genelinde 5 yöntem arasından 2,07 ortalama sıra ile en iyi performansı göstermiştir.
- **Karar:** ✅ `supported`
- **Kanıtlar:**
  - [https://huggingface.co/blog/amazon/higher-order-pruning-experts](https://huggingface.co/blog/amazon/higher-order-pruning-experts)
    > Across all conditions, HOPE achieved the best average rank (2.07 out of 5 methods)

### 6. %50 budama oranında HOPE'un ortalama sırası 1,58'e yükselirken, en iyi ikinci yöntem olan REAP'in ortalama sırası 2,42 olarak gerçekleşmiştir.
- **Karar:** ⚠️ `not_found`
- **Kanıt:** yok

### 7. Qwen3.5-35B-A3B modelinde %50 budama oranında HOPE, SWE-Bench Pro testinde 42,3 puan alarak 41,8 puan alan budanmamış modeli geçmiştir.
- **Karar:** ⚠️ `not_found`
- **Kanıt:** yok

### 8. HOPE yönteminin F-matrisi köşegeni, REAP yönteminin uzman sıralamalarını 0,99 Spearman korelasyonu ile neredeyse mükemmel şekilde kurtarmaktadır.
- **Karar:** ✅ `supported`
- **Kanıtlar:**
  - [https://huggingface.co/blog/amazon/higher-order-pruning-experts](https://huggingface.co/blog/amazon/higher-order-pruning-experts)
    > The diagonal of recovers REAP's expert rankings almost perfectly (Spearman ).

---

## İki Tur Karşılaştırması

| İddia | 1. Tur | 2. Tur | Nihai |
|-------|--------|--------|-------|
| Qwen3.5-122B modeli, 48 MoE katmanının her birinde 256 uzman | supported | supported | supported |
| Qwen3.5-122B modelinin yaklaşık 250 GB'lık parametre belleği | supported | supported | supported |
| HOPE (Higher-Order Pruning of Experts), uzmanlar arasındaki  | supported | supported | supported |
| HOPE yöntemi, %50 budama oranında, en iyi ikinci budama yönt | supported | supported | supported |
| HOPE yöntemi, tüm koşullar genelinde 5 yöntem arasından 2,07 | supported | supported | supported |
| %50 budama oranında HOPE'un ortalama sırası 1,58'e yükselirk | not_found | not_found | not_found |
| Qwen3.5-35B-A3B modelinde %50 budama oranında HOPE, SWE-Benc | not_found | not_found | not_found |
| HOPE yönteminin F-matrisi köşegeni, REAP yönteminin uzman sı | supported | supported | supported |

## Kaynak Metinleri

- `sources/source-1.txt` — https://huggingface.co/blog/amazon/higher-order-pruning-experts
- `sources/source-2.txt` — https://www.engadget.com/2309615/safest-laptop-storage-long-term/
- `sources/source-3.txt` — https://www.wired.com/story/how-to-remind-your-boss-about-your-vacation/
- `sources/source-4.txt` — https://techcrunch.com/2026/11/07/parents-want-safer-phones-for-kids-these-companies-are-answering-the-call/
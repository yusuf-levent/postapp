# Doğrulama Raporu

**Haber:** Palette: teaching a small model to build decks in your design language
**Canonical URL:** https://huggingface.co/blog/ibm-research/palette-deck-building
**Kaynaklar:** Hugging Face Blog, Engadget, Ars Technica, MIT Technology Review
**Kontrol zamanı:** 2026-11-03T19:38:18+03:00
**Sonuç:** ✅ YAYINLANABİLİR

---

## İddia Bazlı Sonuçlar

### 1. Palette, IBM Design Language'i takip eden 20 milyar parametreli bir modeli fine-tune etmiştir.
- **Karar:** ✅ `supported`
- **Kanıtlar:**
  - [https://huggingface.co/blog/ibm-research/palette-deck-building](https://huggingface.co/blog/ibm-research/palette-deck-building)
    > We fine-tuned a 20B model to build decks the way people do: a designer plans the deck and a coder draws each slide. Its training data follows the IBM Design Language, and on PresentBench it ranks first on two of the three domains we measured.
  - [https://huggingface.co/blog/ibm-research/palette-deck-building](https://huggingface.co/blog/ibm-research/palette-deck-building)
    > We fine-tuned a 20B model to build decks the way people do: a designer plans the deck and a coder draws each slide. Its training data follows the IBM Design Language...

### 2. Palette, PresentBench üzerinde ölçülen üç domenden ikisinde birinci sırada yer almaktadır.
- **Karar:** ✅ `supported`
- **Kanıtlar:**
  - [https://huggingface.co/blog/ibm-research/palette-deck-building](https://huggingface.co/blog/ibm-research/palette-deck-building)
    > Its training data follows the IBM Design Language, and on PresentBench it ranks first on two of the three domains we measured.
  - [https://huggingface.co/blog/ibm-research/palette-deck-building](https://huggingface.co/blog/ibm-research/palette-deck-building)
    > ...and on PresentBench it ranks first on two of the three domains we measured.

### 3. Eğitim verileri için yaklaşık 10.000 slaytı kapsayan yaklaşık 1000 sunum üretilmiştir.
- **Karar:** ✅ `supported`
- **Kanıtlar:**
  - [https://huggingface.co/blog/ibm-research/palette-deck-building](https://huggingface.co/blog/ibm-research/palette-deck-building)
    > We generated around 1000 decks covering roughly 10,000 slides.

### 4. Harness, 131 sunum boyunca ortalama 3.5 puan eklemektedir.
- **Karar:** ⚠️ `not_found`
- **Kanıt:** yok

### 5. Üç domen genelinde Palette, NotebookLM'in 1.1 puan gerisinde 59.7 puanla ikinci sırada yer almaktadır.
- **Karar:** ⚠️ `not_found`
- **Kanıt:** yok

### 6. Veri tarifleri 12 kategoriden direktifler içermektedir.
- **Karar:** ✅ `supported`
- **Kanıtlar:**
  - [https://huggingface.co/blog/ibm-research/palette-deck-building](https://huggingface.co/blog/ibm-research/palette-deck-building)
    > The data recipes include directives from 12 categories, a few of which are shown below, each phrased several different ways, so the model learns the intent rather than a fixed phrase.
  - [https://huggingface.co/blog/ibm-research/palette-deck-building](https://huggingface.co/blog/ibm-research/palette-deck-building)
    > The data recipes include directives from 12 categories, a few of which are shown below...

### 7. Kodlayıcı örnekleri tasarımcı örneklerinden yaklaşık 5 kat daha uzundur.
- **Karar:** ✅ `supported`
- **Kanıtlar:**
  - [https://huggingface.co/blog/ibm-research/palette-deck-building](https://huggingface.co/blog/ibm-research/palette-deck-building)
    > One lesson: coder examples are about 5× longer than designer examples, so a naive mix undertrained the designer until we oversampled its examples 5×.
  - [https://huggingface.co/blog/ibm-research/palette-deck-building](https://huggingface.co/blog/ibm-research/palette-deck-building)
    > One lesson: coder examples are about 5× longer than designer examples...

---

## İki Tur Karşılaştırması

| İddia | 1. Tur | 2. Tur | Nihai |
|-------|--------|--------|-------|
| Palette, IBM Design Language'i takip eden 20 milyar parametr | supported | supported | supported |
| Palette, PresentBench üzerinde ölçülen üç domenden ikisinde  | supported | supported | supported |
| Eğitim verileri için yaklaşık 10.000 slaytı kapsayan yaklaşı | supported | supported | supported |
| Harness, 131 sunum boyunca ortalama 3.5 puan eklemektedir. | not_found | not_found | not_found |
| Üç domen genelinde Palette, NotebookLM'in 1.1 puan gerisinde | not_found | not_found | not_found |
| Veri tarifleri 12 kategoriden direktifler içermektedir. | supported | supported | supported |
| Kodlayıcı örnekleri tasarımcı örneklerinden yaklaşık 5 kat d | supported | supported | supported |

## Kaynak Metinleri

- `sources/source-1.txt` — https://huggingface.co/blog/ibm-research/palette-deck-building
- `sources/source-2.txt` — https://www.engadget.com/2303890/easy-way-turn-regular-tv-smart/
- `sources/source-3.txt` — https://arstechnica.com/science/2026/11/research-roundup-6-cool-science-stories-we-almost-missed-7/
- `sources/source-4.txt` — https://www.technologyreview.com/2026/10/30/1147838/eating-disorders-rise-glp-1s-weight-loss-drugs/
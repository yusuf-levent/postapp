# Doğrulama Raporu

**Haber:** Apple has a secret list of banned autocomplete phrases including ‘dictator Trump’ and ‘covid is a hoax’
**Canonical URL:** https://www.theverge.com/tech/1028663/apple-ios-keyboard-blocked-words-autocomplete
**Kaynaklar:** The Verge, Wired, TechCrunch, Engadget
**Kontrol zamanı:** 2026-11-06T18:13:46+03:00
**Sonuç:** ✅ YAYINLANABİLİR

---

## İddia Bazlı Sonuçlar

### 1. Araştırmacı Derik Kauffman, iOS'te otomatik tamamlama ve kaydırarak yazma özelliklerinde engellenmiş 100.000'den fazla kelime ve ifade buldu.
- **Karar:** ✅ `supported`
- **Kanıtlar:**
  - [https://www.theverge.com/tech/1028663/apple-ios-keyboard-blocked-words-autocomplete](https://www.theverge.com/tech/1028663/apple-ios-keyboard-blocked-words-autocomplete)
    > A researcher found over 100,000 words and phrases in “every major language” that are blocked from autocomplete and swipe-type in iOS, Reuters reports. The researcher, Derik Kauffman

### 2. iOS klavyesi, engellenen kelimeleri tek tek harf yazıldığında engellememekte ancak tahmin olarak sunmamaktadır.
- **Karar:** ✅ `supported`
- **Kanıtlar:**
  - [https://www.theverge.com/tech/1028663/apple-ios-keyboard-blocked-words-autocomplete](https://www.theverge.com/tech/1028663/apple-ios-keyboard-blocked-words-autocomplete)
    > The researcher, Derik Kauffman, says you can still type the words on the blocklist one letter at a time. But they won’t pop up as predictive text suggestions

### 3. iOS klavyesinin engellediği ifadeler arasında 'dictator Trump', 'covid is a hoax', 'illegal immigrant', 'sleepy Joe' ve 'left wing conspiracy' gibi siyasi içerikli ifadeler yer almaktadır.
- **Karar:** ✅ `supported`
- **Kanıtlar:**
  - [https://www.theverge.com/tech/1028663/apple-ios-keyboard-blocked-words-autocomplete](https://www.theverge.com/tech/1028663/apple-ios-keyboard-blocked-words-autocomplete)
    > But it also contains political phrases like “illegal immigrant,” “dictator Trump,” “sleepy Joe,” “covid was a hoax,” and “left wing conspiracy”

### 4. Derik Kauffman, engellenen kelime listesini OpenAI'ın Codex ve Anthropic'in Claude Code araçlarını kullanarak iOS sistem dosyaları içerisinden çıkardı.
- **Karar:** ✅ `supported`
- **Kanıtlar:**
  - [https://www.theverge.com/tech/1028663/apple-ios-keyboard-blocked-words-autocomplete](https://www.theverge.com/tech/1028663/apple-ios-keyboard-blocked-words-autocomplete)
    > According to Reuters, Kauffman used OpenAI’s Codex and Anthropic’s Claude Code to help find the list “deep in the bowels” of iOS.

### 5. Engellenen kelime listesi iOS içerisinde bir hash tablosu olarak saklanmaktadır.
- **Karar:** ✅ `supported`
- **Kanıtlar:**
  - [https://www.theverge.com/tech/1028663/apple-ios-keyboard-blocked-words-autocomplete](https://www.theverge.com/tech/1028663/apple-ios-keyboard-blocked-words-autocomplete)
    > On his website, Kauffman says the phrase list was stored as a hash table, which he was able to convert back to text.

### 6. Başka bir araştırmacı, Reuters'a verdiği demeçte aynı listeye bağımsız olarak ulaştığını doğruladı.
- **Karar:** ✅ `supported`
- **Kanıtlar:**
  - [https://www.theverge.com/tech/1028663/apple-ios-keyboard-blocked-words-autocomplete](https://www.theverge.com/tech/1028663/apple-ios-keyboard-blocked-words-autocomplete)
    > Another researcher told Reuters they were able to independently obtain the same list.

### 7. Apple, klavyesinin potansiyel olarak uygunsuz veya saldırgan önerilerden kaçınmak için tasarlandığını belirtti.
- **Karar:** ✅ `supported`
- **Kanıtlar:**
  - [https://www.theverge.com/tech/1028663/apple-ios-keyboard-blocked-words-autocomplete](https://www.theverge.com/tech/1028663/apple-ios-keyboard-blocked-words-autocomplete)
    > Apple told Reuters that its keyboard is designed to avoid potentially inappropriate or offensive suggestions

### 8. iOS klavyesi 'bad girl' ifadesini engellerken 'bad boy' ifadesini engellememektedir.
- **Karar:** ✅ `supported`
- **Kanıtlar:**
  - [https://www.theverge.com/tech/1028663/apple-ios-keyboard-blocked-words-autocomplete](https://www.theverge.com/tech/1028663/apple-ios-keyboard-blocked-words-autocomplete)
    > Kauffman found some discrepancies on the list, too, where one phrase is blocked while its counterpart isn’t, such as blocking “bad girl” but not “bad boy.”

---

## İki Tur Karşılaştırması

| İddia | 1. Tur | 2. Tur | Nihai |
|-------|--------|--------|-------|
| Araştırmacı Derik Kauffman, iOS'te otomatik tamamlama ve kay | supported | supported | supported |
| iOS klavyesi, engellenen kelimeleri tek tek harf yazıldığınd | supported | supported | supported |
| iOS klavyesinin engellediği ifadeler arasında 'dictator Trum | supported | supported | supported |
| Derik Kauffman, engellenen kelime listesini OpenAI'ın Codex  | supported | supported | supported |
| Engellenen kelime listesi iOS içerisinde bir hash tablosu ol | supported | supported | supported |
| Başka bir araştırmacı, Reuters'a verdiği demeçte aynı listey | supported | supported | supported |
| Apple, klavyesinin potansiyel olarak uygunsuz veya saldırgan | supported | supported | supported |
| iOS klavyesi 'bad girl' ifadesini engellerken 'bad boy' ifad | supported | supported | supported |

## Kaynak Metinleri

- `sources/source-1.txt` — https://www.theverge.com/tech/1028663/apple-ios-keyboard-blocked-words-autocomplete
- `sources/source-2.txt` — https://www.wired.com/story/ads-in-chatbots-have-arrived-heres-whats-working-and-whats-not/
- `sources/source-3.txt` — https://techcrunch.com/2026/11/05/openai-released-a-new-cybersecurity-model-is-that-enough/
- `sources/source-4.txt` — https://www.engadget.com/2308154/iphone-duo-new-accessibility-feature-ios-27-3-beta-reachability/
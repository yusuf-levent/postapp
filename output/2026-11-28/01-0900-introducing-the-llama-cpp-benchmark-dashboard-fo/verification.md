# Doğrulama Raporu

**Haber:** Introducing the llama.cpp benchmark dashboard for AMD Ryzen and Radeon
**Canonical URL:** https://huggingface.co/blog/ggml-org/llamacpp-amd-bench
**Kaynaklar:** Hugging Face Blog
**Kontrol zamanı:** 2026-11-28T09:03:17+03:00
**Sonuç:** ✅ YAYINLANABİLİR

---

## İddia Bazlı Sonuçlar

### 1. Llama.cpp × AMD Benchmark paneli Hugging Face platformunda kullanıma sunulmuştur.
- **Karar:** ✅ `supported`
- **Kanıtlar:**
  - [https://huggingface.co/blog/ggml-org/llamacpp-amd-bench](https://huggingface.co/blog/ggml-org/llamacpp-amd-bench)
    > The llama.cpp × AMD Benchmark dashboard is available on Hugging Face.

### 2. Benchmark panelinde şu an için Radeon 8060S (gfx1151) ve Radeon AI Pro R9700S (gfx1201) donanım seçenekleri bulunmaktadır.
- **Karar:** ✅ `supported`
- **Kanıtlar:**
  - [https://huggingface.co/blog/ggml-org/llamacpp-amd-bench](https://huggingface.co/blog/ggml-org/llamacpp-amd-bench)
    > The current hardware choices are Radeon 8060S (gfx1151) and Radeon AI Pro R9700S (gfx1201).

### 3. PP512 testi 512 girdi token'ının işlenme hızını ölçmektedir.
- **Karar:** ✅ `supported`
- **Kanıtlar:**
  - [https://huggingface.co/blog/ggml-org/llamacpp-amd-bench](https://huggingface.co/blog/ggml-org/llamacpp-amd-bench)
    > | PP512 | Process 512 input tokens | How quickly the model processes a prompt |
  - [https://huggingface.co/blog/ggml-org/llamacpp-amd-bench](https://huggingface.co/blog/ggml-org/llamacpp-amd-bench)
    > PP512 | Process 512 input tokens | How quickly the model processes a prompt

### 4. TG128 testi 128 token üretme hızını ölçmektedir.
- **Karar:** ✅ `supported`
- **Kanıtlar:**
  - [https://huggingface.co/blog/ggml-org/llamacpp-amd-bench](https://huggingface.co/blog/ggml-org/llamacpp-amd-bench)
    > | TG128 | Generate 128 tokens | How quickly the model produces output |
  - [https://huggingface.co/blog/ggml-org/llamacpp-amd-bench](https://huggingface.co/blog/ggml-org/llamacpp-amd-bench)
    > TG128 | Generate 128 tokens | How quickly the model produces output

### 5. Benchmark testleri llama-bench aracı kullanılarak, Flash Attention açık ve kapalı şekilde, her konfigürasyon için 10 tekrarla yapılmaktadır.
- **Karar:** ✅ `supported`
- **Kanıtlar:**
  - [https://huggingface.co/blog/ggml-org/llamacpp-amd-bench](https://huggingface.co/blog/ggml-org/llamacpp-amd-bench)
    > The public gfx1151 and gfx1201 workflows are scheduled weekly and run the standard benchmarks using the llama-bench tool with Flash Attention on and off, with 10 repetitions per configuration.

### 6. Benchmark testleri haftalık olarak planlanmaktadır.
- **Karar:** ✅ `supported`
- **Kanıtlar:**
  - [https://huggingface.co/blog/ggml-org/llamacpp-amd-bench](https://huggingface.co/blog/ggml-org/llamacpp-amd-bench)
    > The public gfx1151 and gfx1201 workflows are scheduled weekly
  - [https://huggingface.co/blog/ggml-org/llamacpp-amd-bench](https://huggingface.co/blog/ggml-org/llamacpp-amd-bench)
    > The public gfx1151 and gfx1201 workflows are scheduled weekly and run the standard benchmarks

### 7. Benchmark panelinde yer alan mevcut modeller arasında Inkling 2 Mini, Qwen, Gemma, gpt-oss ve LFM modelleri bulunmaktadır.
- **Karar:** ✅ `supported`
- **Kanıtlar:**
  - [https://huggingface.co/blog/ggml-org/llamacpp-amd-bench](https://huggingface.co/blog/ggml-org/llamacpp-amd-bench)
    > The model set evolves and currently includes Inkling 2 Mini, Qwen, Gemma, gpt-oss, and LFM models

### 8. Benchmark sonuçları Hugging Face üzerindeki ggml-org/install.sh-benches-data depolama alanından okunmaktadır.
- **Karar:** ✅ `supported`
- **Kanıtlar:**
  - [https://huggingface.co/blog/ggml-org/llamacpp-amd-bench](https://huggingface.co/blog/ggml-org/llamacpp-amd-bench)
    > The explorer reads directly from the public ggml-org/install.sh-benches-data Storage Bucket on Hugging Face.

---

## İki Tur Karşılaştırması

| İddia | 1. Tur | 2. Tur | Nihai |
|-------|--------|--------|-------|
| Llama.cpp × AMD Benchmark paneli Hugging Face platformunda k | supported | supported | supported |
| Benchmark panelinde şu an için Radeon 8060S (gfx1151) ve Rad | supported | supported | supported |
| PP512 testi 512 girdi token'ının işlenme hızını ölçmektedir. | supported | supported | supported |
| TG128 testi 128 token üretme hızını ölçmektedir. | supported | supported | supported |
| Benchmark testleri llama-bench aracı kullanılarak, Flash Att | supported | supported | supported |
| Benchmark testleri haftalık olarak planlanmaktadır. | supported | supported | supported |
| Benchmark panelinde yer alan mevcut modeller arasında Inklin | supported | supported | supported |
| Benchmark sonuçları Hugging Face üzerindeki ggml-org/install | supported | supported | supported |

## Kaynak Metinleri

- `sources/source-1.txt` — https://huggingface.co/blog/ggml-org/llamacpp-amd-bench
# Doğrulama Raporu

**Haber:** 1Password says it was hacked but users' vaults are safe
**Canonical URL:** https://www.engadget.com/2329013/1password-hacked-but-users-vaults-are-safe/
**Kaynaklar:** Engadget, TechCrunch
**Kontrol zamanı:** 2026-11-27T09:03:37+03:00
**Sonuç:** ✅ YAYINLANABİLİR

---

## İddia Bazlı Sonuçlar

### 1. 1Password, bir saldırganın sistemine sızarak bazı müşteri verilerini çaldığını kabul etti ve kullanıcıların kasaları ile giriş bilgilerinin güvende olduğunu açıkladı.
- **Karar:** ✅ `supported`
- **Kanıtlar:**
  - [https://www.engadget.com/2329013/1password-hacked-but-users-vaults-are-safe/](https://www.engadget.com/2329013/1password-hacked-but-users-vaults-are-safe/)
    > 1Password has admitted that an attacker was able to infiltrate its system and steal some customer data, but it has assured users in its announcement that their vaults and logins are safe.
  - [https://techcrunch.com/2026/11/25/1password-said-hackers-broke-into-its-internal-systems-but-customer-passwords-are-safe/](https://techcrunch.com/2026/11/25/1password-said-hackers-broke-into-its-internal-systems-but-customer-passwords-are-safe/)
    > Password manager maker 1Password has confirmed that some customer information was taken in a recent intrusion into its internal systems, but that customer password vaults and other secrets were not accessed.

### 2. 1Password, 19 Kasım tarihinde bir çalışanın kurumsal GitHub hesabının ele geçirildiğine dair belirtileri araştırmaya başladığını bildirdi.
- **Karar:** ✅ `supported`
- **Kanıtlar:**
  - [https://www.engadget.com/2329013/1password-hacked-but-users-vaults-are-safe/](https://www.engadget.com/2329013/1password-hacked-but-users-vaults-are-safe/)
    > On November 19, the company started investigating signs that an employee's corporate GitHub account had been compromised.
  - [https://techcrunch.com/2026/11/25/1password-said-hackers-broke-into-its-internal-systems-but-customer-passwords-are-safe/](https://techcrunch.com/2026/11/25/1password-said-hackers-broke-into-its-internal-systems-but-customer-passwords-are-safe/)
    > The Toronto-based tech company said in a blog post published Wednesday that it detected an intrusion on November 19, in which an attacker gained access to an employee’s corporate account with GitHub

### 3. Saldırgan, ele geçirdiği GitHub hesabını kaynak koduna erişmek ve arka ucuna kötü amaçlı kod enjekte etmek için kullandı.
- **Karar:** ✅ `supported`
- **Kanıtlar:**
  - [https://www.engadget.com/2329013/1password-hacked-but-users-vaults-are-safe/](https://www.engadget.com/2329013/1password-hacked-but-users-vaults-are-safe/)
    > The company found that the attacker used that account to access its source code and inject malicious code to its backend.

### 4. Saldırgan; müşterilerin isimleri, e-posta adresleri, hesap oluşturma tarihleri ve son oturum açma zamanları gibi verileri indirdi.
- **Karar:** ✅ `supported`
- **Kanıtlar:**
  - [https://www.engadget.com/2329013/1password-hacked-but-users-vaults-are-safe/](https://www.engadget.com/2329013/1password-hacked-but-users-vaults-are-safe/)
    > The attacker was then able to download customers' data, including people's names and email addresses, the dates their accounts were created and their last sign-in times.
  - [https://techcrunch.com/2026/11/25/1password-said-hackers-broke-into-its-internal-systems-but-customer-passwords-are-safe/](https://techcrunch.com/2026/11/25/1password-said-hackers-broke-into-its-internal-systems-but-customer-passwords-are-safe/)
    > allowed the hacker to download some data about 1Password customers, including their names and the email address that they use for logging into their account. The company said that the attacker also took details about when a 1Password account was created and when a user last logged in.

### 5. Saldırgan kullanıcıların genel anahtarlarını da çaldı ancak 1Password bunun güvenliklerini etkilemediğini belirtti.
- **Karar:** ✅ `supported`
- **Kanıtlar:**
  - [https://www.engadget.com/2329013/1password-hacked-but-users-vaults-are-safe/](https://www.engadget.com/2329013/1password-hacked-but-users-vaults-are-safe/)
    > They were also able to steal users' public keys, but 1Password said it has no impact to their security.

### 6. 1Password, ihlali keşfettikten sonra çalınan token'ı iptal ettiğini, etkilenen GitHub hesabını devre dışı bıraktığını ve benzer saldırılar için yeni tespit araçları eklediğini açıkladı.
- **Karar:** ✅ `supported`
- **Kanıtlar:**
  - [https://www.engadget.com/2329013/1password-hacked-but-users-vaults-are-safe/](https://www.engadget.com/2329013/1password-hacked-but-users-vaults-are-safe/)
    > Since discovering the breach, 1Password has revoked the stolen token, disabled the affected GitHub account and added new detection tools for similar attacks.

### 7. 1Password, kullanıcıların e-postalarının ihlalde ele geçirildiği için sahte hesap kurtarma ve davet e-postaları yoluyla şifre ele geçirme girişimlerine karşı dikkatli olunması gerektiğini tavsiye etti.
- **Karar:** ✅ `supported`
- **Kanıtlar:**
  - [https://www.engadget.com/2329013/1password-hacked-but-users-vaults-are-safe/](https://www.engadget.com/2329013/1password-hacked-but-users-vaults-are-safe/)
    > While 1Password said that users' vaults remain safe, the company still advises being vigilant when it comes to phishing attempts. It warned that since users' emails were compromised in the breach, they could be used in attempts to grab people's passwords through fake account recovery and invitation emails.

---

## İki Tur Karşılaştırması

| İddia | 1. Tur | 2. Tur | Nihai |
|-------|--------|--------|-------|
| 1Password, bir saldırganın sistemine sızarak bazı müşteri ve | supported | supported | supported |
| 1Password, 19 Kasım tarihinde bir çalışanın kurumsal GitHub  | supported | supported | supported |
| Saldırgan, ele geçirdiği GitHub hesabını kaynak koduna erişm | supported | supported | supported |
| Saldırgan; müşterilerin isimleri, e-posta adresleri, hesap o | supported | supported | supported |
| Saldırgan kullanıcıların genel anahtarlarını da çaldı ancak  | supported | supported | supported |
| 1Password, ihlali keşfettikten sonra çalınan token'ı iptal e | supported | supported | supported |
| 1Password, kullanıcıların e-postalarının ihlalde ele geçiril | supported | supported | supported |

## Kaynak Metinleri

- `sources/source-1.txt` — https://www.engadget.com/2329013/1password-hacked-but-users-vaults-are-safe/
- `sources/source-2.txt` — https://techcrunch.com/2026/11/25/1password-said-hackers-broke-into-its-internal-systems-but-customer-passwords-are-safe/
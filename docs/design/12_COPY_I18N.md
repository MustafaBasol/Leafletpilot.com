# Copy & i18n

## Genel Ton

Uygulama metinleri:

- Kısa
- Net
- Teknik olmayan
- Güven veren
- Operasyonel
- Esnafın anlayacağı dilde

## Ana Sayfa / Dashboard Metinleri

### Dashboard Başlığı

```txt
Dashboard
```

### Dashboard Alt Başlığı

```txt
Kampanyalarınızı, ürün eşleşmelerinizi ve broşür çıktılarınızı tek ekrandan takip edin.
```

### Hızlı Aksiyonlar

```txt
Yeni Kampanya
Ürün Ekle
Excel İçe Aktar
Şablonları Gör
Bot Bağlantısını Test Et
```

## Kampanya Durumları

```json
{
  "draft": "Taslak",
  "parsing": "Analiz ediliyor",
  "matching": "Ürünler eşleştiriliyor",
  "missing_products": "Eksik ürün var",
  "preview_ready": "Önizleme hazır",
  "waiting_approval": "Onay bekliyor",
  "revision_requested": "Revizyon istendi",
  "approved": "Onaylandı",
  "generating_files": "Dosyalar oluşturuluyor",
  "completed": "Tamamlandı",
  "failed": "Hata oluştu",
  "cancelled": "İptal edildi"
}
```

## Ürün Eşleşme Durumları

```json
{
  "matched": "Eşleşti",
  "low_confidence": "Kontrol gerekli",
  "not_found": "Bulunamadı",
  "manual_selected": "Manuel seçildi",
  "new_product_needed": "Yeni ürün gerekli"
}
```

## Empty State Metinleri

### Kampanya Yok

```txt
Henüz kampanya oluşturulmadı.
Ürün listenizi yükleyerek veya bot üzerinden göndererek ilk broşürünüzü oluşturabilirsiniz.
```

Buton:

```txt
Yeni Kampanya Oluştur
```

### Ürün Yok

```txt
Katalogda henüz ürün bulunmuyor.
İlk ürünlerinizi manuel ekleyebilir veya Excel dosyasıyla toplu aktarabilirsiniz.
```

Butonlar:

```txt
Ürün Ekle
Excel İçe Aktar
```

### Şablon Yok

```txt
Henüz şablon oluşturulmadı.
Broşür üretimi için en az bir aktif şablon gereklidir.
```

Buton:

```txt
Şablon Ekle
```

### Bot Bağlı Değil

```txt
Mesajlaşma botu henüz bağlı değil.
Kullanıcıların ürün listelerini mesajlaşma uygulaması üzerinden gönderebilmesi için bot bağlantısını tamamlayın.
```

Buton:

```txt
Bot Bağlantısını Kur
```

## Form Label Metinleri

### Kampanya

```txt
Kampanya Adı
Market
Şablon
Kampanya Tarihi
Ürün Listesi
Çıktı Formatları
Notlar
```

### Ürün

```txt
Ürün Adı
Kısa Ürün Adı
Marka
Kategori
Barkod
Paket Boyutu
Paket Tipi
Alternatif İsimler
Ürün Görseli
Durum
```

### Market

```txt
Market Adı
Logo
Ana Renk
İkincil Renk
Adres
Telefon
E-posta
Web Sitesi
Varsayılan Şablon
Para Birimi
Dil
```

## Buton Metinleri

```txt
Kaydet
İptal
Düzenle
Sil
Önizle
İndir
Gönder
Onayla
Yeniden Oluştur
Dosya Üret
Kampanya Oluştur
Ürün Ekle
Eşleştir
Yeni Ürün Olarak Ekle
Görselsiz Devam Et
```

## Toast Mesajları

### Başarı

```txt
Kampanya oluşturuldu.
Ürün kaydedildi.
Önizleme hazırlandı.
PDF dosyası oluşturuldu.
Dosyalar kullanıcıya gönderildi.
Bot bağlantısı başarılı.
```

### Uyarı

```txt
Bazı ürünler için manuel kontrol gerekiyor.
Bu şablon seçilen ürün sayısı için önerilmiyor.
Ürün görseli bulunmuyor.
```

### Hata

```txt
Kampanya oluşturulamadı.
Dosya yüklenemedi.
Ürün eşleştirme tamamlanamadı.
PDF oluşturulurken hata oluştu.
Bot bağlantısı başarısız.
```

## Confirmation Modal Metinleri

### Silme Onayı

Başlık:

```txt
Bu kaydı silmek istiyor musunuz?
```

Açıklama:

```txt
Bu işlem geri alınamaz. Devam etmek istediğinizden emin misiniz?
```

Butonlar:

```txt
Vazgeç
Sil
```

### Final Dosya Üretme Onayı

Başlık:

```txt
Final dosyalar oluşturulsun mu?
```

Açıklama:

```txt
PDF ve PNG dosyaları mevcut önizlemeye göre oluşturulacak.
```

Butonlar:

```txt
Vazgeç
Dosyaları Oluştur
```

## Bot Mesajları

### Karşılama

```txt
Merhaba 👋
Kampanya broşürünüzü hazırlamak için ürün listenizi gönderebilirsiniz.
```

### Liste Örneği

```txt
Örnek:
Coca Cola 2L - 1.59€
Eti Burçak - 0.99€
Ülker Halley - 1.49€
```

### Analiz Başladı

```txt
Listenizi aldım. Ürünleri ve fiyatları analiz ediyorum.
```

### Önizleme Hazır

```txt
Broşür taslağınız hazır. Lütfen ürünleri ve fiyatları kontrol edin.
```

### Final Hazır

```txt
Broşürünüz hazır ✅
PDF ve görsel dosyalarınızı aşağıda bulabilirsiniz.
```

## İngilizce Karşılıklar İçin Not

İlk MVP Türkçe olabilir. Ancak Avrupa pazarı hedeflendiği için sonraki fazda en az şu diller düşünülmelidir:

- Türkçe
- İngilizce
- Fransızca
- Almanca

i18n yapısı baştan hazır kurulmalıdır.

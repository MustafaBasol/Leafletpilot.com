# MVP Scope

## MVP Amacı

Ürünün gerçek müşteriye satılabilir olup olmadığını hızlıca test etmek.

İlk MVP’nin amacı tüm özellikleri yapmak değildir. Amaç:

- Mesajlaşma uygulamasından ürün listesi almak
- Ürünleri katalogla eşleştirmek
- Şablonla broşür üretmek
- Önizleme/onay akışı kurmak
- PDF/PNG dosyaları göndermek
- Admin panelden operasyonu yönetmek

## MVP’de Olacaklar

### 1. Telegram Bot

İlk kanal olarak Telegram önerilir.

Özellikler:
- Metin mesajı alma
- Excel dosyası alma
- PDF dosyası alma opsiyonel
- Önizleme gönderme
- PDF/PNG gönderme
- Basit butonlu onay akışı

### 2. Kampanya Oluşturma

- Liste yapıştırma
- Excel yükleme
- Ürün adı/fiyat ayrıştırma
- Kampanya kaydı
- Durum takibi

### 3. Ürün Eşleştirme

- Exact match
- Fuzzy match
- Alternatif isimlerle eşleştirme
- Düşük güvenli eşleşme uyarısı
- Bulunamayan ürün raporu

### 4. Ürün Kataloğu

- Ürün listeleme
- Ürün ekleme
- Ürün düzenleme
- PNG yükleme
- Marka/kategori seçimi
- Alternatif isimler
- Barkod alanı

### 5. Şablon Motoru

- 2 hazır şablon
- A4 PDF üretimi
- A4 PNG üretimi
- Instagram post üretimi
- Çok ürün varsa otomatik sayfa bölme

### 6. Önizleme ve Onay

- Önizleme PNG üretimi
- Kullanıcıya gönderme
- Onay alma
- Revizyon isteği
- Final dosya üretimi

### 7. Admin Panel

- Dashboard
- Kampanyalar
- Kampanya detayı
- Ürün kataloğu
- Şablonlar
- Bot bağlantıları
- Market ayarları

## MVP’de Olmayacaklar

İlk sürümde ertelenmeli:

- WhatsApp Business API
- Otomatik sosyal medya paylaşımı
- ERP/POS entegrasyonu
- Tedarikçi katalog otomasyonu
- Gelişmiş raporlama
- AI fiyat önerileri
- Çoklu şube
- Çoklu dil broşür üretimi
- Mobil uygulama
- Matbaa standardı CMYK export
- Gelişmiş abonelik/faturalama
- Marka bazlı özel kampanya analizi

## MVP Teknik Öncelik

1. Şablon motoru çalışmalı.
2. Ürün eşleştirme yeterli olmalı.
3. Bot akışı basit ve hatasız olmalı.
4. Panel operasyonu desteklemeli.
5. Dosya üretimi güvenilir olmalı.

## İlk Demo Senaryosu

Demo için sahte market:

```txt
Anadolu Market
```

Demo ürün listesi:

```txt
Coca Cola 2L - 1.59€
Eti Burçak - 0.99€
Ülker Halley 10'lu - 1.49€
Torku Sucuk 400g - 5.99€
Pınar Süt 1L - 0.89€
Nutella 750g - 4.99€
Sütaş Ayran 1L - 0.79€
Bizim Yağ 5L - 8.99€
```

Demo çıktıları:
- A4 broşür PDF
- PNG broşür
- Instagram post

## İlk 300 Ürün Kataloğu

Öncelikli kategoriler:

1. İçecekler
2. Bisküvi & Çikolata
3. Süt Ürünleri
4. Et & Şarküteri
5. Kahvaltılık
6. Bakliyat
7. Temizlik
8. Dondurulmuş
9. Manav
10. Temel gıda

Öncelikli markalar:

- Coca-Cola
- Pepsi
- Ülker
- Eti
- Torku
- Pınar
- Sütaş
- İçim
- Eker
- Nutella
- Tat
- Bizim
- Komili
- Yayla
- Duru
- Namet
- Banvit

## Pilot Müşteri Planı

### Hedef

İlk 5 pilot marketten en az 2 ücretli müşteriye dönüşüm almak.

### Teklif

- İlk broşür ücretsiz
- Sonraki aylık paket: 59€ / 119€ / 199€
- Kurulum: pilotta ücretsiz veya indirimli

### Demo Mesajı

```txt
Merhaba, marketler için haftalık kampanya broşürlerini mesajlaşma uygulaması üzerinden otomatik hazırlayan bir sistem geliştiriyoruz.

Mevcut kampanya ürünlerinizle kısa bir demo hazırlayabiliriz. Ürün listesini gönderiyorsunuz, sistem birkaç dakika içinde PDF ve sosyal medya görseli oluşturuyor.

İsterseniz ilk broşürünüzü ücretsiz deneyebiliriz.
```

## MVP Başarı Kriterleri

- 5 pilot müşteriyle test
- En az 20 kampanya üretimi
- Ürün eşleştirme oranı %80+
- Ortalama taslak üretim süresi 5 dakikanın altında
- En az 2 ücretli dönüşüm
- Müşterinin tekrar kullanım isteği
- Manuel müdahale gerektiren alanların netleşmesi

## Sonraki Fazlar

### Faz 2

- WhatsApp Business API
- Gelişmiş şablonlar
- Instagram Story
- Çoklu sayfa düzenleri
- Toplu ürün import

### Faz 3

- Çoklu market / şube
- Sosyal medya planlama
- Gelişmiş raporlama
- POS entegrasyonu araştırması

### Faz 4

- Tedarikçi katalog entegrasyonu
- AI öneri motoru
- Çok dilli broşür
- Kurumsal paketler

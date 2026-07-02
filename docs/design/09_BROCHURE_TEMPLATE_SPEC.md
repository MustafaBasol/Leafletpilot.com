# Brochure Template Specification

## Genel İlke

Sistem rastgele AI tasarımı üretmemelidir. Profesyonel olarak hazırlanmış, kurallı, tekrar kullanılabilir şablonlar kullanılmalıdır.

AI şu alanlarda destek olabilir:

- Ürün kategorilerini gruplama
- Hero ürün seçme
- Sayfa yoğunluğunu önerme
- Ürün adlarını kısaltma
- Eksik alanları raporlama

Final layout şablon motoru tarafından üretilmelidir.

## Çıktı Formatları

İlk MVP’de zorunlu:

1. A4 PDF
2. A4 PNG
3. Instagram Post 1080x1350

Sonraki faz:

4. Instagram Story 1080x1920
5. Facebook Post 1200x630
6. WhatsApp paylaşım görseli
7. Dijital ekran 1920x1080
8. Baskı PDF CMYK uyumlu export

## Şablon Tipleri

### 1. Klasik Market Broşürü

Kullanım:
- Çok ürünlü haftalık kampanya
- 12-40 ürün

Görsel karakter:
- Büyük başlık
- Kampanya tarihi
- Ürün grid’i
- Kırmızı/sarı fiyat etiketleri
- Market logosu üstte

### 2. Premium Market

Kullanım:
- Daha modern marketler
- Az ürünlü özel kampanya
- 6-18 ürün

Görsel karakter:
- Beyaz alan daha fazla
- Daha büyük ürün fotoğrafları
- Lacivert/yeşil vurgu
- Temiz fiyat kartları

### 3. İndirim Odaklı

Kullanım:
- Agresif kampanya
- Büyük fiyat gösterimi
- 8-24 ürün

Görsel karakter:
- Büyük indirim başlığı
- Güçlü kırmızı/sarı alanlar
- Eski fiyat/yeni fiyat
- Hero ürün alanı

### 4. Kasap / Şarküteri

Kullanım:
- Et, sucuk, peynir, zeytin, şarküteri ürünleri
- 6-20 ürün

Görsel karakter:
- Daha sıcak tonlar
- Ürün kategorisine uygun başlık alanları
- Kg fiyatı desteği

### 5. Manav

Kullanım:
- Meyve/sebze kampanyaları
- Günlük/haftalık taze ürün

Görsel karakter:
- Yeşil vurgu
- Taze ürün hissi
- Kg fiyatları
- Büyük ürün görselleri

## Sayfa Yapısı

### Header

İçerik:
- Market logosu
- Kampanya başlığı
- Tarih aralığı
- Market iletişim bilgisi
- Sosyal medya veya adres

Örnek başlıklar:

```txt
Haftanın Fırsatları
Bu Haftaya Özel İndirimler
Market Kampanyaları
Süper Fırsatlar
```

### Hero Alanı

Opsiyonel.

Kullanım:
- En önemli 1-3 ürün
- Çok iyi fiyatlı ürün
- Stok çekmek istenen ürün

Hero ürün özellikleri:
- Büyük ürün görseli
- Büyük fiyat
- Kampanya etiketi
- Kısa ürün adı

### Product Grid

Ürün kartları sayıya göre otomatik yerleşmeli.

Önerilen grid:

- 6 ürün: 2x3
- 8 ürün: 2x4
- 12 ürün: 3x4
- 16 ürün: 4x4
- 20 ürün: 4x5
- 24+ ürün: çoklu sayfa

### Footer

İçerik:
- Adres
- Telefon
- Sosyal medya
- Kampanya geçerlilik notu
- Stoklarla sınırlıdır notu

Örnek:

```txt
Kampanyalar stoklarla sınırlıdır. Fiyatlar belirtilen tarih aralığında geçerlidir.
```

## Ürün Kartı

### Alanlar

- Ürün görseli
- Ürün adı
- Paket bilgisi
- Yeni fiyat
- Eski fiyat
- Birim fiyat / kg fiyatı
- Kampanya etiketi
- Kategori etiketi opsiyonel

### Fiyat Tipleri

- Tek fiyat
- Eski fiyat / yeni fiyat
- 2 al 1 öde
- Kg fiyatı
- Adet fiyatı
- Koli fiyatı

## Ürün Adı Kısaltma Kuralları

Uzun ürün adları otomatik sadeleştirilebilir.

Örnek:

```txt
Coca-Cola Original Taste Gazlı İçecek 2 Litre
```

Kısaltılmış:

```txt
Coca-Cola 2L
```

AI öneri verir, ama sistem ürün veritabanındaki onaylı kısa adı kullanmalıdır.

## Çok Sayfalı Broşür

Ürün sayısı kapasiteyi aşarsa sistem yeni sayfa oluşturmalıdır.

Kurallar:

- Aynı kategori ürünleri mümkünse aynı sayfada kalmalı.
- Her sayfada header/footer korunmalı.
- Sayfa numarası eklenmeli.
- PDF çok sayfalı üretilebilir.
- PNG çıktıları ayrı sayfalar olarak gönderilebilir.

## Şablon Değişkenleri

Her şablon şu değişkenleri desteklemeli:

```txt
marketName
marketLogo
primaryColor
secondaryColor
campaignTitle
campaignDateRange
products[]
footerText
address
phone
socialLinks
currency
language
```

## Görsel Export Teknik Notları

Önerilen üretim yöntemi:

- HTML/CSS template
- SVG destekli fiyat etiketleri
- Playwright ile screenshot/PDF
- Fontların embed edilmesi
- PDF için print CSS
- PNG için yüksek DPI render

## Baskı Kalitesi

MVP’de profesyonel matbaa standardı zorunlu değildir. Ancak PDF temiz ve baskıya uygun görünmelidir.

Sonraki fazda:
- 300 DPI export
- bleed alanı
- CMYK uyumluluk kontrolü
- baskı güvenli alanları
- crop mark desteği eklenebilir.

## Şablon Önizleme

Panelde her şablon için:
- Dummy ürünlerle örnek önizleme
- Ürün kapasitesi
- Desteklenen formatlar
- Kullanım önerisi
- Aktif/pasif durumu gösterilmeli.

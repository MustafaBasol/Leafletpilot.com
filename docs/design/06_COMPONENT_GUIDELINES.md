# Component Guidelines

## Genel Komponent Dili

Komponentler sade, hızlı anlaşılır ve operasyonel kullanım için optimize edilmiş olmalıdır. Dashboard içinde gereksiz animasyon, aşırı renk ve dekoratif tasarım kullanılmamalıdır.

## Button

### Türler

- Primary
- Secondary
- Outline
- Ghost
- Danger
- Success

### Primary Button

Kullanım:
- Yeni Kampanya
- Dosya Üret
- Onayla
- Kaydet

Stil:
- Background: primary-600
- Text: white
- Radius: 10px
- Height: 40px / 44px
- Font: 14px medium

### Secondary Button

Kullanım:
- Önizleme
- İndir
- Yeniden Oluştur

### Danger Button

Kullanım:
- Sil
- İptal et
- Bağlantıyı kaldır

Danger aksiyonlarda mümkünse confirmation modal kullanılmalı.

## Card

Kartlar dashboard’un temel yapısıdır.

### Standart Kart

- Background: white
- Border: neutral-200
- Radius: 16px
- Shadow: shadow-sm
- Padding: 20px veya 24px

### Metric Card

İçerik:
- Küçük ikon
- Metrik başlığı
- Büyük sayı
- Önceki döneme göre değişim
- İlgili link

Örnek:

```txt
Bu Ay Kampanyalar
24
+%18 geçen aya göre
```

## Table

Tablolar kompakt ve okunabilir olmalı.

### Kurallar

- Header background: neutral-50
- Row hover: primary-50 veya neutral-50
- Satır yüksekliği: 56-64px
- Görsel kolonları küçük thumbnail kullanmalı
- Uzun metinler truncate edilmeli
- Aksiyonlar sağda olmalı
- Durumlar badge ile gösterilmeli

### Bulk Actions

Ürün kataloğu ve kampanya listesinde çoklu seçim olabilir.

Bulk actions:
- Pasifleştir
- Sil
- Kategori değiştir
- Excel dışa aktar

## Badge

Durumları hızlı anlatmak için kullanılmalı.

### Kampanya Durum Badge’leri

- Taslak: neutral
- Analiz Ediliyor: primary
- Eksik Ürün: warning
- Onay Bekliyor: warning
- Onaylandı: success
- Tamamlandı: success
- Hata: danger

### Ürün Eşleşme Badge’leri

- Eşleşti: success
- Kontrol Gerekli: warning
- Bulunamadı: danger
- Manuel Seçildi: primary

## Form

### Input

- Height: 40px / 44px
- Radius: 10px
- Border: neutral-300
- Focus: primary-600 ring
- Label üstte
- Yardım metni altta

### Textarea

Ürün listesi girişi için geniş textarea kullanılmalı.

Örnek placeholder:

```txt
Coca Cola 2L - 1.59€
Eti Burçak - 0.99€
Torku Sucuk 400g - 5.99€
```

### Select

Arama yapılabilir select tercih edilmeli.
Özellikle ürün, kategori, marka, market seçimi için searchable select gerekli.

## Upload Area

Dosya yükleme alanları net olmalı.

### Görsel Yükleme

- Drag & drop
- Dosya tipi açıklaması
- Önerilen format: PNG
- Maksimum boyut
- Önizleme

### Excel/PDF Yükleme

- Kabul edilen formatlar: .xlsx, .csv, .pdf
- Dosya yüklendikten sonra parsing durumu görünmeli

## Modal

Modal şu işlerde kullanılmalı:

- Ürün eşleştirme
- Fiyat düzeltme
- Dosya önizleme
- Silme onayı
- Şablon seçimi
- Yeni marka/kategori ekleme

### Modal Kuralları

- Başlık net olmalı
- Kapatma butonu görünür olmalı
- Ana aksiyon sağ altta
- İptal butonu solunda
- Kritik aksiyonlarda açıklama metni olmalı

## Stepper

Yeni kampanya ekranında kullanılmalı.

Adımlar:

1. Bilgiler
2. Ürünler
3. Eşleştirme
4. Şablon
5. Önizleme
6. Çıktılar

Stepper kullanıcıya sürecin nerede olduğunu göstermeli.

## Tabs

Kampanya detayında kullanılabilir.

Tablar:
- Önizleme
- Ürünler
- Eksikler
- Çıktılar
- Mesajlar
- Geçmiş

## Toast / Notification

Başarılı işlemler:

```txt
Kampanya önizlemesi oluşturuldu.
Ürün kaydedildi.
PDF dosyası üretildi.
```

Hatalar:

```txt
PDF oluşturulurken hata oluştu.
Ürün eşleştirme tamamlanamadı.
Dosya yüklenemedi.
```

Uyarılar:

```txt
3 ürün için manuel kontrol gerekiyor.
Bu şablon önerilen ürün sayısını aşıyor.
```

## Empty State

Empty state’lerde üç şey olmalı:

1. Kısa başlık
2. Açıklama
3. Aksiyon butonu

## Loading State

Uzun süren işlemlerde durum metni kullanılmalı:

- Liste analiz ediliyor
- Ürünler eşleştiriliyor
- Önizleme hazırlanıyor
- PDF oluşturuluyor
- Dosyalar gönderiliyor

Skeleton loader, kampanya ve ürün tablolarında kullanılabilir.

## Progress Indicator

Kampanya üretimi çok adımlı olduğu için progress göstergesi faydalı olur.

Örnek:

```txt
1. Liste alındı
2. Ürünler analiz edildi
3. 18/20 ürün eşleşti
4. Önizleme üretildi
5. Onay bekleniyor
```

## Search

Ürün kataloğunda güçlü arama alanı olmalı.

Arama şu alanlarda çalışmalı:

- Ürün adı
- Alternatif isimler
- Marka
- Barkod
- Kategori

## Product Thumbnail

Ürün görseli olmayan ürünlerde placeholder kullanılmalı.

Placeholder metni:

```txt
Görsel yok
```

Eksik görsel uyarı badge’i gösterilmeli.

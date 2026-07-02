# Admin Panel Specification

## Amaç

Admin panel, sistemin operasyonel merkezidir. Kullanıcılar kampanyaları, ürünleri, şablonları, market bilgilerini ve bot bağlantılarını buradan yönetir.

## Ana Modüller

1. Kampanya Yönetimi
2. Ürün Kataloğu
3. Kategori Yönetimi
4. Marka Yönetimi
5. Şablon Yönetimi
6. Market / Müşteri Yönetimi
7. Bot Bağlantıları
8. Dosya Yönetimi
9. Ayarlar

## Kampanya Yönetimi

### Kampanya Listesi

Kampanyalar tablo halinde gösterilir.

Filtreler:
- Durum
- Market
- Kanal
- Tarih
- Şablon
- Eksik ürün var/yok

### Kampanya Detayı

Kampanya detayında:

- Genel bilgiler
- Önizleme
- Ürün eşleşmeleri
- Eksik ürünler
- Çıktılar
- Mesaj geçmişi
- İşlem geçmişi

### Kampanya Aksiyonları

- Önizleme oluştur
- Final dosyaları üret
- Kullanıcıya gönder
- Revizyon iste
- Onaylandı işaretle
- Kopyala
- Arşivle

## Ürün Kataloğu

### Ürün Modeli

UI açısından bir ürün şu alanları taşımalıdır:

```txt
id
name
shortName
brand
category
barcode
packageSize
packageType
image
alternativeNames
status
qualityScore
createdAt
updatedAt
lastUsedAt
usageCount
```

### Ürün Ekleme

Form alanları:
- Ürün adı
- Kısa ad
- Marka
- Kategori
- Barkod
- Paket boyutu
- Paket tipi
- Görsel
- Alternatif isimler
- Notlar

### Alternatif İsimler

Ürün eşleştirme için kritik.

Örnek:

Ana ürün:

```txt
Coca-Cola 2L
```

Alternatifler:

```txt
Coca Cola 2 litre
Kola 2L
Coco Cola 2 lt
Coca 2l
```

### Görsel Kalite Durumu

Görsel kalitesi şu şekilde gösterilebilir:

- Mükemmel
- İyi
- Kontrol gerekli
- Görsel yok

## Kategori Yönetimi

Kategori alanları:

```txt
name
parentCategory
color
icon
sortOrder
status
```

Örnek kategoriler:

- İçecekler
- Bisküvi & Çikolata
- Süt Ürünleri
- Et & Şarküteri
- Kahvaltılık
- Bakliyat
- Temizlik
- Dondurulmuş
- Manav
- Unlu Mamuller

## Marka Yönetimi

Marka alanları:

```txt
name
logo
country
status
productCount
```

Marka listesinde ürün sayısı gösterilmeli.

## Şablon Yönetimi

Şablon alanları:

```txt
name
type
description
supportedFormats
maxProductsPerPage
previewImage
status
isDefault
createdAt
```

### Şablon Aksiyonları

- Önizle
- Varsayılan yap
- Aktif/pasif
- Kopyala
- Düzenle
- Sil

## Market / Müşteri Yönetimi

Market alanları:

```txt
marketName
legalName
logo
primaryColor
secondaryColor
address
phone
email
website
socialLinks
defaultTemplate
currency
language
timezone
subscriptionPlan
status
```

### Market Detayı

Sekmeler:

- Genel Bilgiler
- Marka Ayarları
- Kampanyalar
- Ürünler
- Bot Bağlantısı
- Kullanıcılar
- Faturalama

İlk MVP’de faturalama sekmesi opsiyonel olabilir.

## Bot Bağlantıları

Kanal türleri:

- Telegram
- WhatsApp
- Future: Email
- Future: Web Upload

Alanlar:

```txt
provider
botName
phoneNumber
status
webhookStatus
lastMessageAt
connectedAt
lastError
```

Aksiyonlar:
- Bağlantıyı test et
- Webhook’u yenile
- Test mesajı gönder
- Bağlantıyı kaldır

## Dosya Yönetimi

Her kampanyanın çıktıları saklanmalıdır.

Dosya alanları:

```txt
campaignId
fileType
format
url
size
createdAt
sentToUserAt
status
```

Dosya türleri:

- preview_png
- brochure_pdf
- brochure_png
- instagram_post
- instagram_story
- facebook_post

## Ayarlar

### Genel Ayarlar

- Varsayılan para birimi
- Varsayılan dil
- Varsayılan şablon
- Dosya saklama süresi
- Önizleme onayı zorunlu mu?

### AI Ayarları

- Eşleşme güven eşiği
- Düşük güven uyarısı
- Otomatik hero ürün seçimi
- Ürün adı kısaltma
- Kategori gruplama

### Export Ayarları

- PDF kalite seviyesi
- PNG çözünürlüğü
- Dosya sıkıştırma
- Çok sayfalı broşür davranışı

## Yetki Matrisi

| Modül | Platform Admin | Market Admin | Staff | Operator |
|---|---|---|---|---|
| Kampanya görme | Tüm | Kendi | Kendi | Atanan |
| Kampanya oluşturma | Evet | Evet | Evet | Evet |
| Ürün ekleme | Evet | Evet | Sınırlı | Evet |
| Şablon yönetimi | Evet | Sınırlı | Hayır | Sınırlı |
| Market ayarı | Evet | Evet | Hayır | Hayır |
| Bot bağlantısı | Evet | Evet | Hayır | Hayır |
| Kullanıcı yönetimi | Evet | Evet | Hayır | Hayır |

## Operasyonel Öncelikler

Panel ilk sürümde özellikle şu işleri hızlı yaptırmalı:

1. Eksik ürün eşleştirme
2. PNG yükleme
3. Kampanya önizleme kontrolü
4. PDF/PNG yeniden üretme
5. Bot bağlantı durumunu görme
6. Kullanıcıya dosya gönderme

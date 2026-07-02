# Information Architecture

## Ana Menü Yapısı

Önerilen sol menü:

1. Dashboard
2. Kampanyalar
3. Yeni Kampanya
4. Ürün Kataloğu
5. Kategoriler
6. Markalar
7. Şablonlar
8. Müşteriler / Marketler
9. Bot Bağlantıları
10. Dosyalar
11. Raporlar
12. Ayarlar

## Menü Grupları

### Operasyon

- Dashboard
- Kampanyalar
- Yeni Kampanya

### Katalog

- Ürün Kataloğu
- Kategoriler
- Markalar

### Tasarım

- Şablonlar
- Dosyalar

### Yönetim

- Müşteriler / Marketler
- Bot Bağlantıları
- Raporlar
- Ayarlar

## Kullanıcı Rolleri

### Platform Admin

Tüm sistemi yönetir.

Yetkiler:
- Tüm marketleri görür
- Tüm kampanyaları görür
- Şablon oluşturur
- Sistem ürün veritabanını yönetir
- Kullanıcıları yönetir
- Paketleri yönetir

### Market Admin

Kendi marketini yönetir.

Yetkiler:
- Kendi kampanyalarını görür
- Kendi ürünlerini ekler
- Market logosu/renklerini ayarlar
- Şablon seçer
- Bot bağlantısını görür
- Kullanıcı ekler

### Market Staff

Operasyonel kullanım.

Yetkiler:
- Kampanya oluşturur
- Ürün listesi gönderir
- Taslak onaylar
- Ürünleri sınırlı düzenler

### Designer / Operator

İlk concierge MVP’de iç ekip rolü.

Yetkiler:
- Kampanya taslağını düzeltir
- Eksik ürünleri eşleştirir
- Şablonları kontrol eder
- PDF/PNG üretimi tekrar başlatır

## Sayfa Ağacı

```txt
/
├── login
├── dashboard
├── campaigns
│   ├── list
│   ├── new
│   └── detail/:id
├── products
│   ├── list
│   ├── new
│   └── detail/:id
├── categories
├── brands
├── templates
│   ├── list
│   ├── new
│   └── detail/:id
├── markets
│   ├── list
│   └── detail/:id
├── bot-connections
├── files
├── reports
└── settings
```

## İlk MVP’de Gerekli Sayfalar

Zorunlu:

- Login
- Dashboard
- Kampanyalar
- Kampanya Detayı
- Yeni Kampanya
- Ürün Kataloğu
- Ürün Ekle/Düzenle
- Şablonlar
- Bot Bağlantısı
- Market Ayarları

Sonraya bırakılabilir:

- Raporlar
- Dosyalar
- Çoklu müşteri yönetimi
- Gelişmiş kullanıcı rolleri
- Paket yönetimi
- API entegrasyonları

## Kampanya Durumları

```txt
draft
parsing
matching
missing_products
preview_ready
waiting_approval
revision_requested
approved
generating_files
completed
failed
cancelled
```

Türkçe görünümler:

- Taslak
- Analiz ediliyor
- Ürünler eşleştiriliyor
- Eksik ürün var
- Önizleme hazır
- Onay bekliyor
- Revizyon istendi
- Onaylandı
- Dosyalar üretiliyor
- Tamamlandı
- Hata oluştu
- İptal edildi

## Ürün Eşleşme Durumları

```txt
matched
low_confidence
not_found
manual_selected
new_product_needed
```

Türkçe görünümler:

- Eşleşti
- Kontrol gerekli
- Bulunamadı
- Manuel seçildi
- Yeni ürün gerekli

## Dosya Türleri

- Broşür PDF
- Broşür PNG
- Instagram Post
- Instagram Story
- Facebook Post
- WhatsApp Görseli
- Baskı PDF
- Önizleme Görseli

## Temel Navigasyon Kuralları

- En önemli aksiyon her zaman görünür olmalı: “Yeni Kampanya”
- Kampanya detayında dosya üretim ve onay durumu üstte görünmeli.
- Eksik ürünler ayrı ve dikkat çekici bölümde gösterilmeli.
- Ürün kataloğunda arama çok güçlü olmalı.
- Şablon önizlemeleri görsel kartlarla sunulmalı.

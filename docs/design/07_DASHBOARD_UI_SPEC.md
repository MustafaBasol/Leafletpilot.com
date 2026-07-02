# Dashboard UI Specification

## Dashboard Amacı

Dashboard, kullanıcının broşür üretim operasyonunun güncel durumunu hızlıca görmesini sağlar.

Ana sorular:

1. Kaç kampanya üretildi?
2. Hangi kampanyalar onay bekliyor?
3. Hangi ürünler eksik?
4. Bot bağlantısı çalışıyor mu?
5. Bugün yapılması gereken operasyon var mı?

## Sayfa Başlığı

```txt
Dashboard
```

Alt başlık:

```txt
Kampanyalarınızı, ürün eşleşmelerini ve çıktı durumlarını tek ekrandan takip edin.
```

## Üst Aksiyonlar

Sağ üstte:

- Yeni Kampanya
- Ürün Ekle
- Bot Testi

## Metrik Kartları

### 1. Bu Ay Kampanyalar

Başlık:

```txt
Bu Ay Kampanyalar
```

Alt metin:

```txt
Oluşturulan toplam kampanya
```

### 2. Onay Bekleyen

Başlık:

```txt
Onay Bekleyen
```

Alt metin:

```txt
Müşteri kontrolü bekleyen taslaklar
```

### 3. Eksik Ürün

Başlık:

```txt
Eksik Ürün
```

Alt metin:

```txt
Katalogda bulunamayan ürünler
```

### 4. Üretilen Dosyalar

Başlık:

```txt
Üretilen Dosyalar
```

Alt metin:

```txt
PDF ve görsel çıktılar
```

## Ana Grid Yapısı

Desktop önerisi:

```txt
[Metric Card] [Metric Card] [Metric Card] [Metric Card]

[Son Kampanyalar - 2/3 genişlik] [Bot Durumu - 1/3]

[Onay Bekleyenler - 1/2] [Eksik Ürünler - 1/2]

[Hızlı Aksiyonlar] [Son İşlem Geçmişi]
```

## Son Kampanyalar Kartı

### Kolonlar

- Kampanya
- Market
- Durum
- Ürün
- Tarih
- Aksiyon

### Örnek Satırlar

```txt
Hafta 28 İndirimleri | Anadolu Market | Onay Bekliyor | 24 ürün | Bugün
Kasap Özel Kampanya | Helal Kasap | Tamamlandı | 12 ürün | Dün
```

### Aksiyonlar

- Detay
- Önizleme
- Dosya indir

## Bot Durumu Kartı

### Durumlar

Connected:

```txt
Bot aktif
Son mesaj: 3 dakika önce
```

Disconnected:

```txt
Bot bağlı değil
Webhook bağlantısı kontrol edilmeli
```

Warning:

```txt
Bot aktif ama son 24 saatte mesaj alınmadı
```

### İçerik

- Kanal: Telegram / WhatsApp
- Durum
- Son mesaj
- Webhook URL durumu
- Test mesajı butonu

## Onay Bekleyenler

Kartta en fazla 5 kampanya gösterilmeli.

Her satır:
- Kampanya adı
- Market
- Önizleme küçük görseli
- Bekleme süresi
- Onay ekranına git butonu

## Eksik Ürünler

Bu bölüm operasyon için çok önemlidir.

Her satır:
- Gelen ürün adı
- Kampanya
- Önerilen eşleşme varsa
- Aksiyon: Eşleştir / Yeni ürün ekle

## Hızlı Aksiyonlar

Grid butonları:

1. Yeni Kampanya Oluştur
2. Ürün Kataloğuna Git
3. Excel İçe Aktar
4. Yeni Şablon Ekle
5. Bot Bağlantısını Kontrol Et
6. Market Ayarları

## İşlem Geçmişi

Örnek aktiviteler:

- “Hafta 28 İndirimleri” kampanyası tamamlandı.
- “Coca Cola 2L” ürünü manuel eşleştirildi.
- “Premium Market” şablonuyla PDF üretildi.
- Telegram botundan yeni ürün listesi alındı.

## Dashboard Empty State

Hiç veri yoksa:

Başlık:

```txt
İlk kampanyanızı oluşturmaya hazırsınız
```

Açıklama:

```txt
Ürün listenizi girerek veya bot üzerinden göndererek dakikalar içinde ilk broşürünüzü oluşturabilirsiniz.
```

Butonlar:

```txt
Yeni Kampanya Oluştur
Ürün Kataloğu Hazırla
```

## Dashboard Tasarım Notları

- Metrik kartları sade olmalı.
- Eksik ürün ve onay bekleyenler görsel olarak dikkat çekmeli.
- Bot durumu her zaman kolay görülmeli.
- Kullanıcı dashboard’dan kampanya detayına tek tıkla gidebilmeli.
- Mobilde metrik kartları 2 kolon, operasyon listeleri tek kolon olmalı.

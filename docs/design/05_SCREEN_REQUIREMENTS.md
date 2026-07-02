# Screen Requirements

## 1. Login Ekranı

### Amaç

Kullanıcının güvenli şekilde sisteme giriş yapması.

### Layout

Sol tarafta ürün değeri anlatan görsel/gradient alan, sağda login kartı olabilir.

### Alanlar

- E-posta
- Şifre
- Beni hatırla
- Giriş yap butonu
- Şifremi unuttum linki

### Metin

Başlık:

```txt
Kampanya broşürlerinizi dakikalar içinde hazırlayın
```

Alt metin:

```txt
Ürün listenizi gönderin, sistem profesyonel PDF ve sosyal medya görsellerinizi otomatik oluştursun.
```

## 2. Dashboard

### Amaç

Güncel kampanya durumunu, eksik işleri ve performansı göstermek.

### Üst Kartlar

- Bu Ay Oluşturulan Kampanya
- Onay Bekleyen Taslak
- Eksik Ürün
- Üretilen Dosya
- Aktif Market / Şube

### Ana Bölümler

1. Son Kampanyalar
2. Onay Bekleyenler
3. Eksik Ürünler
4. Hızlı Aksiyonlar
5. Bot Bağlantı Durumu

### Hızlı Aksiyonlar

- Yeni Kampanya
- Ürün Ekle
- Excel İçe Aktar
- Şablonları Gör
- Bot Test Mesajı Gönder

## 3. Kampanyalar Listesi

### Amaç

Tüm kampanyaların durumunu ve çıktılarını takip etmek.

### Filtreler

- Durum
- Market
- Tarih aralığı
- Şablon
- Kanal
- Eksik ürün var/yok

### Tablo Kolonları

- Kampanya adı
- Market
- Ürün sayısı
- Durum
- Kanal
- Oluşturma tarihi
- Son güncelleme
- Dosyalar
- Aksiyonlar

### Aksiyonlar

- Detay
- Önizleme
- PDF indir
- PNG indir
- Yeniden oluştur
- Sil

## 4. Kampanya Detayı

### Amaç

Tek kampanyanın tüm sürecini yönetmek.

### Üst Bölüm

- Kampanya adı
- Durum badge’i
- Market adı
- Şablon
- Oluşturma tarihi
- Kanal
- Ana aksiyon butonu

### Bölümler

1. Önizleme
2. Ürünler
3. Eksik / Düşük Güvenli Ürünler
4. Çıktılar
5. Mesaj Geçmişi
6. İşlem Geçmişi

### Ürün Tablosu

Kolonlar:

- Görsel
- Gelen ürün adı
- Eşleşen ürün
- Fiyat
- Eski fiyat
- Kategori
- Eşleşme skoru
- Durum
- Aksiyon

### Kritik Aksiyonlar

- Önizlemeyi yeniden oluştur
- Final dosyaları üret
- Kullanıcıya gönder
- Onaylandı olarak işaretle
- Revizyon iste

## 5. Yeni Kampanya Ekranı

### Amaç

Panelden manuel kampanya oluşturmak.

### Adımlar

Stepper yapısı önerilir:

1. Bilgiler
2. Ürün Listesi
3. Eşleştirme
4. Şablon
5. Önizleme
6. Onay ve Çıktılar

### Alanlar

- Kampanya adı
- Market / şube
- Şablon
- Kampanya tarihi
- Ürün listesi metin alanı
- Excel yükleme
- PDF yükleme
- Çıktı formatları

## 6. Ürün Kataloğu

### Amaç

Onaylı ürün veritabanını yönetmek.

### Filtreler

- Arama
- Marka
- Kategori
- Görsel var/yok
- Barkod var/yok
- Aktif/pasif
- Son kullanılan

### Tablo Kolonları

- Ürün görseli
- Ürün adı
- Marka
- Barkod
- Kategori
- Alternatif isim sayısı
- Kullanım sayısı
- Durum
- Aksiyonlar

### Aksiyonlar

- Ürün ekle
- Toplu Excel aktar
- PNG yükle
- Düzenle
- Pasifleştir
- Sil

## 7. Ürün Ekle / Düzenle

### Alanlar

- Ürün adı
- Marka
- Kategori
- Barkod
- Paket boyutu
- Paket tipi
- Alternatif isimler
- Ürün görseli
- Görsel kalite notu
- Aktif/pasif
- Notlar

### Görsel Yükleme

- Drag & drop alanı
- PNG önerilir uyarısı
- Arka plan şeffaf mı kontrol göstergesi
- Görsel boyut bilgisi
- Önizleme

## 8. Şablonlar

### Amaç

Broşür tasarım şablonlarını yönetmek.

### Şablon Kartı İçeriği

- Önizleme görseli
- Şablon adı
- Kullanım amacı
- Ürün kapasitesi
- Formatlar
- Aktif/pasif
- Varsayılan etiketi

### Şablon Tipleri

- Klasik Market
- Premium
- İndirim Odaklı
- Minimal
- Kasap/Şarküteri
- Manav

## 9. Bot Bağlantıları

### Amaç

Telegram/WhatsApp bağlantı durumunu göstermek ve test etmek.

### Alanlar

- Kanal türü
- Bot adı / numara
- Bağlantı durumu
- Son mesaj zamanı
- Webhook durumu
- Test mesajı gönder
- QR veya bağlantı talimatları

## 10. Market Ayarları

### Alanlar

- Market adı
- Logo
- Adres
- Telefon
- Web sitesi
- Sosyal medya hesapları
- Ana renk
- İkincil renk
- Varsayılan şablon
- Varsayılan çıktı formatları
- Para birimi
- Dil
- Zaman dilimi

## 11. Dosya Önizleme Modalı

### Amaç

PDF/PNG çıktıları hızlı görmek.

### İçerik

- Büyük görsel önizleme
- Sayfa navigasyonu
- Yakınlaştır / uzaklaştır
- PDF indir
- PNG indir
- Kullanıcıya gönder
- Yeniden oluştur

## 12. Empty State Kuralları

### Kampanya yok

```txt
Henüz kampanya oluşturulmadı.
İlk kampanyanızı ürün listenizi yükleyerek veya bot üzerinden göndererek oluşturabilirsiniz.
```

Buton:

```txt
Yeni Kampanya Oluştur
```

### Ürün yok

```txt
Katalogda henüz ürün bulunmuyor.
İlk ürünleri manuel ekleyebilir veya Excel ile toplu aktarabilirsiniz.
```

Butonlar:

```txt
Ürün Ekle
Excel İçe Aktar
```

### Bot bağlı değil

```txt
Mesajlaşma botu henüz bağlanmadı.
Kullanıcıların ürün listelerini mesajlaşma uygulaması üzerinden gönderebilmesi için bot bağlantısını tamamlayın.
```

Buton:

```txt
Bot Bağlantısını Kur
```

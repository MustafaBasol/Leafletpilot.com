# Messaging Bot Flow

## Genel Yaklaşım

İlk MVP’de Telegram kullanılabilir. Sistem daha sonra WhatsApp Business API ile genişletilecek şekilde kanal bağımsız tasarlanmalıdır.

Kanal bağımsız kavramlar:

- IncomingMessage
- IncomingFile
- OutgoingMessage
- OutgoingFile
- ConversationState
- CampaignDraft
- ApprovalAction

## Bot Tonu

Bot dili:

- Kısa
- Net
- Yardımcı
- Esnaf dostu
- Gereksiz teknik terim kullanmayan

## İlk Karşılama

```txt
Merhaba 👋
Kampanya broşürünüzü hazırlamak için ürün listenizi gönderebilirsiniz.

Örnek:
Coca Cola 2L - 1.59€
Eti Burçak - 0.99€
Ülker Halley - 1.49€

Excel veya PDF dosyası da gönderebilirsiniz.
```

## Liste Alındı Mesajı

```txt
Listenizi aldım. Ürünleri ve fiyatları analiz ediyorum.
```

## Analiz Sonucu — Başarılı

```txt
Analiz tamamlandı.

Toplam ürün: 24
Eşleşen ürün: 22
Kontrol gereken ürün: 2

Önizleme oluşturmamı ister misiniz?
```

Butonlar:
- Önizleme Oluştur
- Ürünleri Kontrol Et
- İptal Et

## Analiz Sonucu — Eksik Ürün Var

```txt
Bazı ürünleri katalogda bulamadım.

Kontrol gereken ürünler:
1. Torku Sucuk 400g
2. Bizim Yağ 5L

Bu ürünleri görselsiz kullanabilir, manuel eşleştirebilir veya katalogdan yeni ürün olarak ekleyebilirsiniz.
```

Butonlar:
- Görselsiz Devam Et
- Manuel Kontrol
- İptal Et

## Önizleme Hazır

```txt
Broşür taslağınız hazır.

Lütfen ürünleri ve fiyatları kontrol edin. Onaylarsanız PDF ve PNG dosyalarını oluşturacağım.
```

Dosya:
- preview.png

Butonlar:
- Onayla
- Fiyat Düzelt
- Ürün Değiştir
- İptal Et

## Onay Mesajı

```txt
Onayınız alındı. PDF ve görsel dosyalar hazırlanıyor.
```

## Final Dosya Mesajı

```txt
Broşürünüz hazır ✅

Dosyalar:
- Baskı PDF
- PNG görsel
- Instagram paylaşım görseli
```

Dosyalar:
- brochure.pdf
- brochure-page-1.png
- instagram-post.png

## Fiyat Düzeltme Akışı

Bot:

```txt
Hangi ürünün fiyatını düzeltmek istiyorsunuz?
Ürün numarasını veya adını yazabilirsiniz.
```

Kullanıcı:

```txt
Coca Cola 2L 1.49€
```

Bot:

```txt
Coca Cola 2L fiyatı 1.59€ yerine 1.49€ olarak güncellendi.

Önizlemeyi yeniden oluşturayım mı?
```

Butonlar:
- Yeniden Oluştur
- Başka Düzeltme Yap

## Ürün Değiştirme Akışı

Bot:

```txt
Hangi ürünü değiştirmek istiyorsunuz?
```

Kullanıcı:

```txt
Torku Sucuk
```

Bot:

```txt
Torku Sucuk için birkaç benzer ürün buldum:

1. Torku Dana Sucuk 400g
2. Torku Fermente Sucuk 300g
3. Torku Piliç Sucuk 500g

Lütfen seçmek istediğiniz numarayı yazın.
```

## Hata Mesajları

### Liste Anlaşılamadı

```txt
Gönderdiğiniz listeden ürün ve fiyatları net şekilde ayıramadım.

Lütfen şu formata yakın şekilde tekrar gönderin:

Ürün adı - fiyat
Coca Cola 2L - 1.59€
Eti Burçak - 0.99€
```

### Dosya Okunamadı

```txt
Dosyanızı okuyamadım. Lütfen Excel, CSV veya PDF formatında tekrar gönderin.
```

### PDF Üretim Hatası

```txt
Broşür dosyası oluşturulurken teknik bir hata oluştu. Ekibimiz kontrol edecek.
```

## Bot Komutları

### /start

Karşılama ve kullanım açıklaması.

### /new

Yeni kampanya başlatır.

### /status

Aktif kampanya durumunu gösterir.

### /help

Kullanım örneği gönderir.

### /cancel

Aktif işlemi iptal eder.

## Conversation State Önerisi

```txt
idle
waiting_for_product_list
parsing_list
waiting_for_column_confirmation
matching_products
waiting_for_missing_product_action
preview_generating
waiting_for_approval
waiting_for_price_correction
waiting_for_product_replacement
generating_final_files
completed
cancelled
failed
```

## Kanal Bağımsız Tasarım Notu

Backend içinde mesajlaşma kanalı şu şekilde soyutlanmalıdır:

```txt
MessagingProvider
├── TelegramProvider
├── WhatsAppProvider
└── FutureProvider
```

Bot akışları kanal bağımsız olmalı, sadece buton/medya gönderim yöntemi sağlayıcı bazında değişmelidir.

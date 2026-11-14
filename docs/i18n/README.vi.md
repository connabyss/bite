# Bite (Tiếng Việt)

[English](../../README.md) · **Tiếng Việt** · [Español](README.es.md) · [简体中文](README.zh-CN.md)

> Bản dịch ngắn này được làm với sự trợ giúp của AI. Nếu bạn thấy chỗ nào dịch chưa đúng, hãy mở issue hoặc pull request. Bản tiếng Anh là bản đầy đủ và mới nhất.

### Nếu lỗi quay lại, các bài kiểm thử (test) của bạn có phát hiện ra không?

Bite kiểm tra xem lời "đã sửa" của một AI viết code có thật sự đúng không.
Nó lấy từng bản sửa lỗi ra khỏi một bản sao dự án của bạn, rồi chạy các test của bạn. Miễn phí, không cần khóa API.

## Thử ngay

Miễn phí, không cần khóa, và không bao giờ thay đổi file của bạn. Bạn cần Python 3.10 trở lên và git. Dán hai dòng này vào
bất kỳ cửa sổ dòng lệnh nào (PowerShell, cmd, Terminal):

```
python -m pip install bite-check
python -m bite_check --free
```

Nếu chạy bên ngoài một dự án, Bite sẽ cho xem bản demo trên một dự án nhỏ dựng sẵn. Để kiểm tra dự án của bạn, gõ dòng thứ hai
và một dấu cách, kéo thư mục dự án vào cửa sổ (việc này sẽ gõ đường dẫn giúp bạn), rồi nhấn Enter.

## Vì sao bạn cần nó

Khi một AI sửa lỗi cho bạn, nó thường nói: "Đã sửa, và tôi đã thêm một test." Nếu bạn không đọc code, bạn không thể biết
điều đó có đúng không.

Một test giống như một con robot nhỏ kiểm tra một việc và la lên khi có gì sai. Bite cố tình đặt lỗi cũ trở lại và
xem có test nào la lên không. Giống như thử chuông báo khói bằng khói thật, thay vì tin vào cái đèn xanh nhỏ.

Nếu có test la lên, bản sửa đó đã được bảo vệ. Nếu tất cả đều im lặng, lỗi có thể quay lại mà không ai biết.
Bite chỉ ra bản sửa đó, để bạn có thể nói với AI của mình: "hãy thêm một test sẽ thất bại nếu không có bản sửa này."

## Đọc kết quả

- ✅ **noticed by** (đã được phát hiện bởi) tên một test: bản sửa đã được một test bảo vệ.
- ⚠️ **NO TEST NOTICED** (không test nào phát hiện): lấy bản sửa ra mà mọi test vẫn qua. Lỗi có thể quay lại mà không ai biết.

Mỗi lần chạy đều tạo một trang báo cáo, `bite_proof/report.html`, để mở trong trình duyệt.

## Tìm hiểu thêm

Mọi thứ khác (GitHub Action, kiểm tra trực tiếp trong Claude Code, bước trả phí với khóa API của riêng bạn) có trong
[README tiếng Anh](../../README.md) và [hướng dẫn cài đặt](../install.md).

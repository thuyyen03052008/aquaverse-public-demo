"""Evidence-bounded field triage for common aquaculture questions.

This is NOT a disease diagnosis, verified breeding protocol or a general AI model.
Only cite the IDs that are actually returned by the retriever.
"""
from __future__ import annotations


def reproduction_guidance(items: list[dict], question: str) -> str | None:
    import unicodedata
    folded = unicodedata.normalize('NFD', question.casefold())
    folded = ''.join(ch for ch in folded if unicodedata.category(ch) != 'Mn').replace('đ', 'd')
    if not any(x in folded for x in ('khong de', 'chua de', 'khong sinh san', 'khong thay trung', 'chua thay trung')):
        return None
    found = {item['source_id'] for item in items}
    if not found:
        return ('Chưa có nguồn đủ liên quan để phân tích tình huống sinh sản này. '
                'Bạn vui lòng cho biết loài chính xác, hình thức bể, độ tuổi/kích thước và nguồn gốc đàn bố mẹ. '
                'Không nên tự dùng hormone hay hóa chất kích thích đẻ dựa trên câu trả lời thiếu dữ liệu.')
    lines = [
        '**Lươn vào mùa sinh sản nhưng chưa đẻ: những yếu tố nên kiểm tra**',
        'Chỉ biết đang vào mùa sinh sản thì **chưa đủ để kết luận nguyên nhân**. '
        'Đây là các hướng kiểm tra dựa trên tài liệu, không phải chẩn đoán tình trạng bể của bạn.'
    ]
    if 'FISHBASE-REPRO' in found or 'FRONTIERS-2022' in found:
        ref = 'FISHBASE-REPRO' if 'FISHBASE-REPRO' in found else 'FRONTIERS-2022'
        lines.append(f'1. **Đàn bố mẹ đã thành thục và có đúng giới tính chưa?** Lươn đồng có thể chuyển từ cái sang đực trong vòng đời. Không thể xác định chắc giới tính và mức độ thành thục chỉ bằng lịch mùa hoặc ước lượng kích cỡ. [{ref}]')
    if 'JJI-1997' in found or 'FISHBASE-REPRO' in found:
        ref = 'JJI-1997' if 'JJI-1997' in found else 'FISHBASE-REPRO'
        lines.append(f'2. **Có điều kiện làm tổ và nơi trú phù hợp không?** Lươn đực có tập tính làm tổ bọt và bảo vệ trứng. Bể nuôi thương phẩm không tự động tương đương môi trường sinh sản. [{ref}]')
    if 'APST-2017' in found:
        lines.append('3. **Hình thức ghép đàn và điều kiện nuôi sinh sản thế nào?** Có nghiên cứu ghi nhận lươn sinh sản tự nhiên trong ao bê tông với đàn bố mẹ được lựa chọn, nhưng kết quả của thí nghiệm không phải công thức áp dụng cho mọi bể. [APST-2017]')
    lines += [
        '**Để khoanh vùng vấn đề, mình cần thêm:**',
        '- Bạn nuôi lươn đồng trong **bể không bùn, ao đất hay hệ thống khác**? Có giá thể/nơi làm tổ không?',
        '- Đàn bố mẹ được chọn như thế nào, đã xác định **đực/cái và thành thục sinh dục** bằng cách nào?',
        '- Có dấu hiệu làm tổ bọt, thay đổi hoạt động, tổn thương hoặc bỏ ăn không? Có số đo nước gần đây không?',
        'Trong khi chưa rõ nguyên nhân, nên ghi nhận điều kiện bể, hạn chế can thiệp gây stress và nhờ cán bộ thủy sản hoặc chuyên gia sinh sản kiểm tra đàn bố mẹ. **Không tự tiêm hormone hay sử dụng thuốc kích thích sinh sản.**',
    ]
    return '\n\n'.join(lines)

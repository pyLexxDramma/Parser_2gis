document.getElementById('searchForm').addEventListener('submit', async function(event) {
    event.preventDefault();
    const form = event.target;
    const formData = new FormData(form);
    const messageDiv = document.getElementById('message');

    messageDiv.textContent = 'Начинаем поиск...';
    messageDiv.style.color = 'blue';

    try {
        const response = await fetch('/process', {
            method: 'POST',
            body: formData
        });

        const result = await response.json();

        if (response.ok) {
            messageDiv.textContent = `Запрос принят! ID отчета: ${result.report_id}. Вы получите уведомление на email.`;
            messageDiv.style.color = 'green';
        } else {
            messageDiv.textContent = `Ошибка: ${result.detail || 'Не удалось обработать запрос.'}`;
            messageDiv.style.color = 'red';
        }
    } catch (error) {
        messageDiv.textContent = `Произошла ошибка при отправке запроса: ${error}`;
        messageDiv.style.color = 'red';
    }
});
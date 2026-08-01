function selectAll() {
    var checkboxes = document.querySelectorAll('input[type=checkbox]');
    var masterCheckbox = checkboxes[0]; // Предполагаем, что 0-й чекбокс является "мастер" чекбоксом

    console.log("Мастер чекбокс состояние:", masterCheckbox.checked); // Лог состояния мастер чекбокса
    // alert("Мастер чекбокс состояние:", masterCheckbox.checked); // Лог состояния мастер чекбокса

    for (var i = 1; i < checkboxes.length; i++) {
        var style = window.getComputedStyle(checkboxes[i]);

        // Лог для проверки стилей
        console.log(`Чекбокс ${i}: display=${style.display}, visibility=${style.visibility}, opacity=${style.opacity}`);
        alert(`Чекбокс ${i}: display=${style.display}, visibility=${style.visibility}, opacity=${style.opacity}`);

        if (masterCheckbox.checked && style.display !== "none" && style.visibility !== "hidden" && style.opacity !== "0") {
            checkboxes[i].checked = true;
        } else {
            checkboxes[i].checked = false; // Снимаем отметку, если мастер не отмечен или элемент скрыт
        }
    }
}

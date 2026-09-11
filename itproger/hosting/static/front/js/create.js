function selectAll() {
    var checkboxes = document.querySelectorAll('input[type=checkbox]');
    var masterCheckbox = checkboxes[0]; // Assume the first checkbox is the master checkbox

    console.log("Master checkbox state:", masterCheckbox.checked); // Master checkbox state log
    // alert("Master checkbox state:", masterCheckbox.checked); // Master checkbox state log

    for (var i = 1; i < checkboxes.length; i++) {
        var style = window.getComputedStyle(checkboxes[i]);

        // Log for checking styles
        // console.log(`Checkbox ${i}: display=${style.display}, visibility=${style.visibility}, opacity=${style.opacity}`);
        // alert(`Checkbox ${i}: display=${style.display}, visibility=${style.visibility}, opacity=${style.opacity}`);

        if (masterCheckbox.checked && style.display !== "none" && style.visibility !== "hidden" && style.opacity !== "0") {
               // alert("Master checkbox state:", masterCheckbox.checked); // Master checkbox state log

            checkboxes[i].checked = true;
        } else {
            checkboxes[i].checked = false; // Clear the checkbox if the master is unchecked or the element is hidden
        }
    }
}

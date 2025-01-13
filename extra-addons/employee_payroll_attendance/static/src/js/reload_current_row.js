odoo.define('employee_payroll_attendance.ListViewReloadRow', function (require) {
    "use strict";

    const ListController = require('web.ListController');

    ListController.include({
        /**
         * Overriding button click to reload only the current row
         */
        _onButtonClicked: function (event) {
            const self = this;
            const recordID = event.data.record.id; // ID của dòng hiện tại

            // Gọi phương thức RPC để xử lý logic trong Python
            return this._rpc({
                model: event.data.model,
                method: event.data.attrs.name, // Tên phương thức trong Python (vd: toggle_approval)
                args: [[recordID]], // Gửi ID dòng hiện tại tới phương thức Python
            }).then(() => {
                // Reload lại dòng hiện tại
                self.reloadRecord(recordID);
            }).catch(function (error) {
                console.error("Error occurred while reloading current row:", error);
            });
        },
    });
});

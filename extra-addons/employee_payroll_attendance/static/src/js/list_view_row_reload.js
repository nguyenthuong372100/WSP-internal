odoo.define('employee_payroll_attendance.RowReload', function (require) {
    "use strict";

    const ListController = require('web.ListController');

    ListController.include({
        /**
         * Override `_onButtonClicked` để chỉ làm mới dòng hiện tại
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
                // Chỉ làm mới dòng hiện tại
                self.reloadRecord(recordID);
            }).catch(function (error) {
                console.error("Error while reloading current row:", error);
            });
        },
    });
});

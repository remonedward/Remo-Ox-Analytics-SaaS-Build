from __future__ import annotations

"""Excel file upload, dataset management, and deletion view."""

from core.i18n import t
from storage.base import UserSession
from ui.views.base import BaseView


class UploadView(BaseView):
    """View managing the upload, security validation, and deletion of Excel datasets."""

    def get_title(self) -> str:
        return t("upload_title", lang=self.language)

    def get_icon(self) -> str:
        return "📤"

    def render(self) -> None:
        """Render upload dropzone, replacement actions, and dataset manager."""
        try:
            import streamlit as st

            user = self.session.get_user()
            if not user:
                return

            st.title(f"📤 {t('upload_title', lang=self.language)}")
            st.write(t("upload_prompt", lang=self.language))

            # Upload constraints callout
            max_mb = self.settings.max_upload_mb
            quota_msg = (
                f"الحد الأقصى لحجم الملف: {max_mb} ميغابايت | الصيغة المدعومة: .xlsx"
                if self.language == "ar"
                else f"Maximum file size: {max_mb} MB | Supported format: .xlsx"
            )
            st.caption(f"🔒 {quota_msg}")

            # Date format parsing option
            dayfirst = st.checkbox(
                "التواريخ مكتوبة بصيغة يوم/شهر/سنة (DD/MM/YYYY)"
                if self.language == "ar"
                else "Dates are in DD/MM/YYYY format",
                value=False,
            )

            # Dropzone
            uploaded_file = st.file_uploader(
                label="Excel Upload",
                type=["xlsx"],
                label_visibility="collapsed",
            )

            if uploaded_file is not None:
                file_bytes = uploaded_file.getvalue()
                filename = uploaded_file.name

                st.write(f"📄 **{filename}** ({len(file_bytes) // 1024:,} KB)")

                col_proc, col_replace = st.columns([2, 2])
                with col_proc:
                    btn_process = st.button(
                        "⚡ " + ("معالجة وتحليل الملف" if self.language == "ar" else "Process & Analyze File"),
                        type="primary",
                        use_container_width=True,
                        key="btn_process_upload",
                    )
                with col_replace:
                    btn_replace = st.button(
                        "🔄 " + ("استبدال الملف النشط بهذا الملف" if self.language == "ar" else "Replace Active Dataset"),
                        type="secondary",
                        use_container_width=True,
                        key="btn_replace_upload",
                        help="حذف الملف النشط حالياً واستبداله بهذا الملف المرفوع"
                        if self.language == "ar"
                        else "Delete current active dataset and replace it with this file",
                    )

                if btn_process:
                    with st.spinner(t("loading", lang=self.language)):
                        ok, record, err = self.dataset_service.process_and_save_upload(
                            user=user,
                            filename=filename,
                            file_bytes=file_bytes,
                            dayfirst=dayfirst,
                        )

                    if ok and record:
                        st.success(t("upload_success", lang=self.language))
                        self.session.set_active_dataset_id(record.id)
                        self.session.set_current_view("mapping")
                        st.rerun()
                    else:
                        st.error(err or t("upload_error_corrupt", lang=self.language))

                elif btn_replace:
                    active_id = self.session.get_active_dataset_id()
                    with st.spinner("جارٍ الاستبدال..." if self.language == "ar" else "Replacing..."):
                        if active_id:
                            self.dataset_service.delete_dataset(active_id, user.id)
                            self.session.set_active_dataset_id(None)

                        ok, record, err = self.dataset_service.process_and_save_upload(
                            user=user,
                            filename=filename,
                            file_bytes=file_bytes,
                            dayfirst=dayfirst,
                        )

                    if ok and record:
                        st.success("تم استبدال الملف بنجاح!" if self.language == "ar" else "Dataset replaced successfully!")
                        self.session.set_active_dataset_id(record.id)
                        self.session.set_current_view("mapping")
                        st.rerun()
                    else:
                        st.error(err or t("upload_error_corrupt", lang=self.language))

            st.divider()

            # Render Dataset Management Section
            self._render_uploaded_datasets(user)

        except Exception:
            pass

    def _render_uploaded_datasets(self, user: UserSession) -> None:
        """Render table of user datasets with active status and delete actions."""
        import streamlit as st

        datasets = self.dataset_service.list_datasets(user.id)
        active_id = self.session.get_active_dataset_id()

        header_title = (
            f"📂 ملفات البيانات المرفوعة ({len(datasets)})"
            if self.language == "ar"
            else f"📂 Uploaded Datasets ({len(datasets)})"
        )
        st.subheader(header_title)

        if not datasets:
            st.info(
                "لم تقم برفع أي ملفات حتى الآن. اختر ملف Excel أعلاه للبدء."
                if self.language == "ar"
                else "No datasets uploaded yet. Choose an Excel file above to begin."
            )
            return

        for ds in datasets:
            is_active = (ds.id == active_id)
            total_rows = sum(ds.row_counts.values()) if ds.row_counts else 0

            with st.container():
                col_info, col_status, col_actions = st.columns([3, 1, 2])

                with col_info:
                    st.markdown(f"### 📄 `{ds.original_name}`")
                    meta_text = (
                        f"📊 الشيتات: **{len(ds.sheet_names)}** | إجمالي الصفوف: **{total_rows:,}** | الحجم: **{ds.file_size_bytes // 1024:,} KB**"
                        if self.language == "ar"
                        else f"📊 Sheets: **{len(ds.sheet_names)}** | Total Rows: **{total_rows:,}** | Size: **{ds.file_size_bytes // 1024:,} KB**"
                    )
                    st.caption(meta_text)

                with col_status:
                    if is_active:
                        st.success("⭐ " + ("النشط حالياً" if self.language == "ar" else "Active"))
                    else:
                        if st.button(
                            "⭐ " + ("تنشيط" if self.language == "ar" else "Activate"),
                            key=f"act_ds_{ds.id}",
                            use_container_width=True,
                        ):
                            self.session.set_active_dataset_id(ds.id)
                            st.rerun()

                with col_actions:
                    col_del, _ = st.columns([1, 1])
                    with col_del:
                        if st.button(
                            "🗑️ " + ("حذف الملف" if self.language == "ar" else "Delete"),
                            key=f"del_ds_{ds.id}",
                            type="secondary",
                            use_container_width=True,
                            help="حذف هذا الملف نهائياً من حسابك"
                            if self.language == "ar"
                            else "Permanently delete this dataset",
                        ):
                            self.dataset_service.delete_dataset(ds.id, user.id)
                            if active_id == ds.id:
                                self.session.set_active_dataset_id(None)
                            st.success(
                                f"تم حذف الملف '{ds.original_name}' بنجاح!"
                                if self.language == "ar"
                                else f"Dataset '{ds.original_name}' deleted successfully!"
                            )
                            st.rerun()

                st.divider()

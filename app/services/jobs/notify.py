"""Telegram notifications for the job exchange. Failures are logged, never raised:
a blocked bot or a deleted chat must not break the API call that triggered them."""
import html
import logging

from aiogram import Bot
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings
from app.data.regions import LANDS
from app.database.models import ContactRequest, Employer, EmployerLead, SeekerProfile, Vacancy
from app.database.repositories.jobs import JobsRepository, aware
from app.database.repositories.users import UserRepository
from app.i18n import t

log = logging.getLogger(__name__)
e = html.escape

EMPLOYMENT_RU = {"full": "полная", "part": "частичная", "mini": "минджоб", "any": "любая"}


def mod_kb(kind: str, obj_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="✅ Одобрить", callback_data=f"mod:{kind}:{obj_id}:1"),
        InlineKeyboardButton(text="❌ Отклонить", callback_data=f"mod:{kind}:{obj_id}:0"),
    ]])


async def render_for_admin(s: AsyncSession, kind: str, obj) -> str:
    """Text an admin sees when reviewing an item (Russian: admin language)."""
    if kind == "seeker":
        o: SeekerProfile = obj
        return (f"<b>Анкета соискателя #{o.id}</b>\nДолжность: {e(o.position)}\n"
                f"Место: {e(o.city or '—')}, {LANDS.get(o.land or '', '—')}\nНемецкий: {o.german_level or '—'}\n"
                f"Занятость: {EMPLOYMENT_RU.get(o.employment, o.employment)}; смены: {'да' if o.shifts_ok else 'нет'}\n"
                f"Опыт: {e(o.experience)}\nО себе: {e(o.about or '—')}\n\n"
                "Проверьте: нет телефонов, e-mail, ссылок, документов и лишних личных данных.")
    if kind == "lead":
        o: EmployerLead = obj
        where = ", ".join(x for x in (o.city, LANDS.get(o.land or "")) if x) or "—"
        extra = "".join(f"\n{k}: {e(v)}" for k, v in (("Сайт", o.website), ("Ищут", o.positions),
                                                            ("Подробности", o.details)) if v)
        return (f"<b>Анкета компании #{o.id}</b>\n"
                f"Связь: <b>{e(o.contact)}</b>\nTelegram: <a href=\"tg://user?id={o.owner_tg}\">написать</a>\n\n"
                f"Фирма: {e(o.company or '—')}\nКонтактное лицо: {e(o.contact_person or '—')}\nГде: {e(where)}{extra}\n\n"
                "Проверьте фирму и свяжитесь. «Одобрить» — работодатель получит сообщение, что мы с ним свяжемся.")
    if kind == "employer":
        o: Employer = obj
        return (f"<b>Работодатель #{o.id}</b>\nФирма: {e(o.company)}\nАдрес: {e(o.address)}\n"
                f"Регистрация: {e(o.register_no)}\nКонтактное лицо: {e(o.contact_person)}\n"
                f"Контакт: {e(o.contact)}\nСайт: {e(o.website or '—')}\n\n"
                "Проверьте фирму в handelsregister.de / northdata и по сайту.")
    if kind == "vacancy":
        o: Vacancy = obj
        emp = await s.get(Employer, o.employer_id)
        return (f"<b>Вакансия #{o.id}</b> от {e(emp.company if emp else '?')}\n{e(o.title)}\n"
                f"Место: {e(o.city)}, {LANDS.get(o.land or '', '—')}\nНемецкий от: {o.german_level or '—'}\n"
                f"Занятость: {EMPLOYMENT_RU.get(o.employment, o.employment)}\nЗарплата: {e(o.salary or '—')}\n\n"
                f"{e(o.description)}\n\nПроверьте: нет платы за трудоустройство, нет дискриминации (AGG), условия законны.")
    o: ContactRequest = obj
    emp = await s.get(Employer, o.employer_id)
    sk = await s.get(SeekerProfile, o.seeker_id)
    vac = await s.get(Vacancy, o.vacancy_id) if o.vacancy_id else None
    what = "Предложение работодателя → соискателю" if o.kind == "offer" else "Отклик соискателя → на вакансию"
    return (f"<b>{what} #{o.id}</b>\nРаботодатель: {e(emp.company if emp else '?')}\n"
            f"Соискатель: #{sk.id if sk else '?'} {e(sk.position if sk else '')}\nВакансия: {e(vac.title if vac else '—')}\n\n"
            f"«{e(o.message)}»\n\nПроверьте: нет просьб о деньгах, документах, переездах за свой счёт.")


class Notifier:
    def __init__(self, bot: Bot | None, settings: Settings):
        self.bot = bot
        self.settings = settings

    async def _send(self, chat_id: int, text: str, kb=None) -> None:
        if not self.bot:
            return
        try:
            await self.bot.send_message(chat_id, text, reply_markup=kb, parse_mode="HTML",
                                        disable_web_page_preview=True)
        except Exception as ex:  # noqa: BLE001
            log.warning("notify failed: %s", type(ex).__name__)

    async def _lang(self, s: AsyncSession, tg: int) -> str:
        u = await UserRepository(s).get(tg)
        return (u.language if u and u.language else self.settings.default_language)

    async def to_admins(self, s: AsyncSession, kind: str, obj) -> None:
        text = "🆕 На модерацию\n\n" + await render_for_admin(s, kind, obj)
        for admin in self.settings.admin_ids:
            await self._send(admin, text, mod_kb(kind, obj.id))

    async def report(self, s: AsyncSession, v: Vacancy, reporter: int, reason: str, text: str | None) -> None:
        emp = await s.get(Employer, v.employer_id)
        why = {"fee": "просят деньги", "documents": "просят документы / данные банка",
               "fake": "похоже на фейк", "other": "другое"}.get(reason, reason)
        msg = (f"⚠️ <b>Жалоба на вакансию #{v.id}</b>\n{e(v.title)} — {e(emp.company if emp else '?')}\n"
               f"Причина: {why}\n{e(text or '')}\n\n"
               f"От: <a href=\"tg://user?id={reporter}\">пользователь</a>.")
        kb = InlineKeyboardMarkup(inline_keyboard=[[
            InlineKeyboardButton(text="🚫 Снять вакансию", callback_data=f"rep:close:{v.id}")]])
        for admin in self.settings.admin_ids:
            await self._send(admin, msg, kb)

    async def moderated(self, s: AsyncSession, kind: str, obj, approved: bool) -> None:
        jobs = JobsRepository(s)
        owner = await jobs.owner_of(kind, obj)
        lang = await self._lang(s, owner)
        if kind == "seeker":
            await self._send(owner, t(lang, "job_seeker_approved" if approved else "job_seeker_rejected"))
        elif kind == "lead":
            await self._send(owner, t(lang, "job_lead_approved", contact=e(obj.contact)) if approved
                             else t(lang, "job_lead_rejected"))
        elif kind == "employer":
            if approved:
                until = aware(obj.access_until).strftime("%d.%m.%Y")
                await self._send(owner, t(lang, "job_employer_approved", company=e(obj.company), until=until,
                                          price=self.settings.employer_price_eur))
            else:
                await self._send(owner, t(lang, "job_employer_rejected"))
        elif kind == "vacancy":
            if approved:
                await self._send(owner, t(lang, "job_vacancy_approved", title=e(obj.title),
                                          until=aware(obj.expires_at).strftime("%d.%m.%Y")))
            else:
                await self._send(owner, t(lang, "job_vacancy_rejected", title=e(obj.title)))
        elif kind == "contact":
            if not approved:
                await self._send(owner, t(lang, "job_contact_rejected"))
            else:
                await self.deliver(s, obj)

    async def deliver(self, s: AsyncSession, c: ContactRequest) -> None:
        jobs = JobsRepository(s)
        rcpt = await jobs.recipient_of(c)
        lang = await self._lang(s, rcpt)
        emp = await s.get(Employer, c.employer_id)
        sk = await s.get(SeekerProfile, c.seeker_id)
        vac = await s.get(Vacancy, c.vacancy_id) if c.vacancy_id else None
        kb = InlineKeyboardMarkup(inline_keyboard=[[
            InlineKeyboardButton(text=t(lang, "job_btn_accept"), callback_data=f"jc:{c.id}:1"),
            InlineKeyboardButton(text=t(lang, "job_btn_decline"), callback_data=f"jc:{c.id}:0"),
        ]])
        vac_title = e(vac.title) if vac else t(lang, "job_vacancy_none")
        if c.kind == "offer":
            text = t(lang, "job_offer_received", company=e(emp.company), city=e(vac.city if vac else ""),
                     vacancy=vac_title, message=e(c.message))
        else:
            text = t(lang, "job_apply_received", vacancy=vac_title, position=e(sk.position), city=e(sk.city or "—"),
                     level=sk.german_level or "—", message=e(c.message))
        await self._send(rcpt, text, kb)

    async def answered(self, s: AsyncSession, c: ContactRequest) -> None:
        emp = await s.get(Employer, c.employer_id)
        sk = await s.get(SeekerProfile, c.seeker_id)
        if not emp or not sk:
            return
        e_lang, s_lang = await self._lang(s, emp.owner_tg), await self._lang(s, sk.owner_tg)
        sender_tg = emp.owner_tg if c.kind == "offer" else sk.owner_tg
        if c.status == "declined":
            await self._send(sender_tg, t(e_lang if c.kind == "offer" else s_lang, "job_declined"))
            return
        # accepted: both sides get each other's contacts
        website = f"\n{e(emp.website)}" if emp.website else ""
        await self._send(sk.owner_tg, t(s_lang, "job_contacts_employer", company=e(emp.company), address=e(emp.address),
                                        person=e(emp.contact_person), contact=e(emp.contact), website=website))
        link = f'<a href="tg://user?id={sk.owner_tg}">{e(sk.position)}</a>'
        if self.bot:
            try:
                chat = await self.bot.get_chat(sk.owner_tg)
                if chat.username:
                    link = f"@{chat.username}"
            except Exception:  # noqa: BLE001
                pass
        await self._send(emp.owner_tg, t(e_lang, "job_contacts_seeker", position=e(sk.position),
                                         city=e(sk.city or "—"), link=link))

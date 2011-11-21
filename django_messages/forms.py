import datetime
import uuid

from django import forms
from django.conf import settings
from django.utils.translation import ugettext_lazy as _

if "notification" in settings.INSTALLED_APPS:
    from notification import models as notification
else:
    notification = None

from django_messages.models import Message
from django_messages.fields import CommaSeparatedUserField
from django_messages.utils import format_quote

from mstranslator.models import Language

class MessageForm(forms.ModelForm):
    """
    base message form
    """
    recipients = CommaSeparatedUserField(label=_(u"Recipient"))
    subject = forms.CharField(label=_(u"Subject"))
    body = forms.CharField(label=_(u"Body"),
        widget=forms.Textarea(attrs={'rows': '12', 'cols':'55'}))
    language = forms.ModelChoiceField(
                queryset = Language.objects.all()
            )

    class Meta:
        model = Message
        fields = ('recipients', 'subject', 'body', 'language', )

    def __init__(self, sender, *args, **kw):
        recipient_filter = kw.pop('recipient_filter', None)
        self.sender = sender
        super(MessageForm, self).__init__(*args, **kw)
        if recipient_filter is not None:
            self.fields['recipients']._recipient_filter = recipient_filter

    def create_recipient_message(self, recipient, message):
        return Message(
            owner = recipient,
            sender = self.sender,
            to = recipient.username,
            recipient = recipient,
            subject = message.subject,
            body = message.body,
            thread = message.thread,
            sent_at = message.sent_at,
            language = message.language,
            language_translated = message.language_translated,
            body_translated = message.body_translated,
        )

    def get_thread(self, message):
        return message.thread or uuid.uuid4().hex

    def save(self, commit=True):
        recipients = self.cleaned_data['recipients']
        instance = super(MessageForm, self).save(commit=False)
        instance.sender = self.sender
        instance.owner = self.sender
        instance.recipient = recipients[0]
        instance.thread = self.get_thread(instance)
        instance.unread = False
        instance.sent_at = datetime.datetime.now()

        if (
                instance.language != None
                and instance.body_translated == None
                and hasattr(instance.recipient.get_profile(), 'preferred_language') 
                and instance.recipient.get_profile().preferred_language 
            ):
            instance.language_translated = instance.recipient.get_profile().preferred_language
            instance.body_translated = instance.language.translate_message_to(instance.body, instance.language_translated)

        message_list = []

        # clone messages in recipients inboxes
        for r in recipients:
            if r == self.sender: # skip duplicates
                continue
            msg = self.create_recipient_message(r, instance)
            message_list.append(msg)

        instance.to = ','.join([r.username for r in recipients])

        if commit:
            instance.save()
            for msg in message_list:
                msg.save()
                if notification:
                    notification.send([msg.recipient], 
                            "messages_received", {'message': msg,})
         
        return instance, message_list

    @property
    def standard_layout(self):
        """
        A reasonable generic layout for messages; if uni_form is not installed,
        this will fail silently and return ``None``.
        """
        try:
            from uni_form.helper import FormHelper
            from uni_form.layout import Layout, ButtonHolder, Submit
            helper = FormHelper()
            helper.form_method = "POST"
            helper.layout = Layout(
                        'recipients',
                        'subject',
                        'language',
                        'body',
                        ButtonHolder(
                                Submit('send', 'Send')
                            )
                    )
            return helper
        except ImportError:
            return None


class ComposeForm(MessageForm):
    """
    A simple default form for private messages.
    """

    class Meta:
        model = Message
        fields = ('recipients', 'subject', 'body', 'language', )
    

class ReplyForm(MessageForm):
    """
    reply to form
    """
    class Meta:
        model = Message
        fields = ('recipients', 'subject', 'body', 'language', )

    def __init__(self, sender, message, *args, **kw):
        self.parent_message = message
        initial = kw.pop('initial', {})
        initial['recipients'] = message.sender.username
        initial['body'] = self.quote_message(message)
        initial['subject'] = self.quote_subject(message.subject)
        kw['initial'] = initial
        super(ReplyForm, self).__init__(sender, *args, **kw)
    
    def quote_message(self, original_message):
        return format_quote(original_message.sender, original_message.body)

    def quote_subject(self, subject):
        return u'Re: %s' % subject

    def create_recipient_message(self, recipient, message):
        msg = super(ReplyForm, self).create_recipient_message(recipient, message)
        msg.replied_at = datetime.datetime.now()

        # find parent in recipient messages
        try:
            msg.parent_msg = Message.objects.get(
                owner=recipient,
                sender=message.recipient,
                recipient=message.sender,
                thread=message.thread)
        except (Message.DoesNotExist, Message.MultipleObjectsReturned):
            # message may be deleted 
            pass

        return msg


    def get_thread(self, message):
        return self.parent_message.thread

    def save(self, commit=True):
        instance, message_list = super(ReplyForm, self).save(commit=False)
        instance.replied_at = datetime.datetime.now()
        instance.parent_msg = self.parent_message
        if commit:
            instance.save()
            for msg in message_list:
                msg.save()
                if notification:
                    notification.send([msg.recipient],
                            "messages_reply_received", {
                                'message': msg,
                                'parent_msg': self.parent_message,
                                })
        return instance, message_list



from django.conf import settings
from django.core.exceptions import ObjectDoesNotExist
from django.template import Library, Node, TemplateSyntaxError, Variable
from django.template.defaultfilters import truncatewords_html, linebreaksbr
from django_messages.models import inbox_count_for

register = Library()     

FREE_MEMBER_TRUNCATE_MESSAGE_WORDS = getattr(
        settings, 
        'FREE_MEMBER_TRUNCATE_MESSAGE_WORDS',
        100
    )

class InboxOutput(Node):
    def __init__(self, varname=None):
        self.varname = varname
        
    def render(self, context):
        try:
            user = context['user']
            count = inbox_count_for(user)
        except (KeyError, AttributeError):
            count = ''
        if self.varname is not None:
            context[self.varname] = count
            return ""
        else:
            return "%s" % (count)        
        
@register.tag(name = 'inbox_count')
def do_print_inbox_count(parser, token):
    """
    A templatetag to show the unread-count for a logged in user.
    Returns the number of unread messages in the user's inbox.
    Usage::
    
        {% load inbox %}
        {% inbox_count %}
    
        {# or assign the value to a variable: #}
        
        {% inbox_count as my_var %}
        {{ my_var }}
        
    """
    bits = token.contents.split()
    if len(bits) > 1:
        if len(bits) != 3:
            raise TemplateSyntaxError, "inbox_count tag takes either no arguments or exactly two arguments"
        if bits[1] != 'as':
            raise TemplateSyntaxError, "first argument to inbox_count tag must be 'as'"
        return InboxOutput(bits[2])
    else:
        return InboxOutput()

class MessageNode(Node):
    def __init__(self, message):
        self.message = Variable(message)

    def render(self, context):
        message = self.message.resolve(context)
        try:
            plan = context["user"].get_profile().subscription
            if not plan or plan.membership_plan.free:
                message = truncatewords_html(message.body, FREE_MEMBER_TRUNCATE_MESSAGE_WORDS)
        except (AttributeError, ObjectDoesNotExist):
            pass
        return linebreaksbr(message)

@register.tag(name = 'render_message')
def do_render_message(parser, token):
    """
    Renders a message to the template; please do not do this rendering manually
    as there are special business rules to follow.

    Usage::
        {% load inbox %}
        {% render_message MESSAGE %}

    """
    bits = token.contents.split()
    if len(bits) != 2:
        raise TemplateSyntaxError("{% render_message %} requires a single argument, the message object to render.");
    return MessageNode(bits[1])

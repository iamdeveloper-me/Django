from django.db import models
from django.utils.text import wrap
from django.utils.safestring import mark_safe
from django.db.models.signals import pre_save, pre_delete

from pursuits.cms.models import Document
from pursuits.utils import (make_choice, UndeletedManager, PursuitsManager,
        post_form_save_signal, create_timeline_item,
        post_save_document_signal, get_media_path)


class ProductList(models.Model):
    name = models.CharField(max_length=63)
    default_list = models.BooleanField(default=False)
    sandbox = models.ForeignKey("general.Sandbox")

    objects = PursuitsManager()

    def __unicode__(self):
        return self.name

    def _get_edit_url(self):
        '''Return an url to the edit page for this object'''
        return u'/catalogue/product_list/edit/%d/' % (self.id)
    edit_url = property(_get_edit_url)

    @classmethod
    def setup_post_save(cls, sender, instance,
            original_instance, request, is_new_model,
            model_form, **kwargs):
        create_timeline_item(user=request.user,
                    group_type="Product List",
                    base_url=(u"/catalogue/product_list/edit/%d/"
                              % instance.id),
                    item_name=instance.name,
                    action="Created" if is_new_model else "Updated")

post_form_save_signal.connect(ProductList.setup_post_save,
                              sender=ProductList)



class Product(models.Model):
    class Meta:
        ordering=("product_list", "position",)

    sandbox = models.ForeignKey("general.Sandbox")
    deleted = models.BooleanField(default=False)
    type = models.CharField(max_length=10,
        choices = make_choice(("Product", "Service")))
    name = models.CharField(max_length=255)
    product_list = models.ForeignKey(ProductList)
    position = models.PositiveIntegerField()
    description = models.TextField(blank=True)
    qualification_questions = models.TextField(
            "General Qualification Questions", blank=True)
    documents = models.ManyToManyField(Document, blank=True, null=True)
    profile_image = models.ForeignKey(Document, blank=True, null=True,
                                      related_name="product_image")

    def __unicode__(self):
        return self.name

    def _get_edit_url(self):
        '''Return an url to the edit page for this object'''
        return u'/catalogue/product/edit/%d/' % (self.id)
    edit_url = property(_get_edit_url)
    objects = UndeletedManager()

    def get_product_pic(self):
        if (self.profile_image and not self.profile_image.is_deleted
            and self.profile_image.thumbnail_filename):
            return self.profile_image.thumbnail_filename
        return u"%s/images/empty_product.gif" % get_media_path()

    @property
    def nice_description(self):
        return wrap(self.description, 70)

    @classmethod
    def document_post_save(cls, sender, instance,
            doc_instance, creator, is_new_model,
            action="", **kwargs):
        create_timeline_item(user=creator,
                    group_type=instance.type,
                    base_url=(u"/catalogue/product/edit/%d/"
                              % instance.id),
                    item_name=instance.name,
                    attachment=doc_instance,
                    action=(action or ("Document Uploaded"
                        if is_new_model else "Document Updated")))

    @classmethod
    def setup_post_save(cls, sender, instance,
            original_instance, request, is_new_model,
            model_form, **kwargs):
        create_timeline_item(user=request.user,
                    group_type=instance.type,
                    base_url=(u"/catalogue/product/edit/%d/"
                              % instance.id),
                    item_name=instance.name,
                    action="Created" if is_new_model else "Updated")

    @classmethod
    def setup_pre_save(cls, sender, instance, **kwargs):
        instance.name = instance.name.strip()


pre_save.connect(Product.setup_pre_save, sender=Product)
post_form_save_signal.connect(Product.setup_post_save,
                              sender=Product)
post_save_document_signal.connect(Product.document_post_save,
                                  sender=Product)


def set_product_position(sender, instance, **kwargs):
    '''If the product is a new product (no id set), set the position to the
    maximum available. Further, if the product is deleted, set the position to
    zero and rearrange all later products.'''
    if not instance.id:
        products = Product.objects.undeleted().order_by("position")
        if products:
            max_pos = list(products)[-1].position
        else:
            max_pos = 0
        instance.position = max_pos + 1
    elif instance.deleted:
        higher_products = Product.objects.undeleted().filter(
                position__gt=instance.position)
        for product in higher_products:
            product.position -= 1
            product.save() # Should it use save_base?
        instance.position = 0


pre_save.connect(set_product_position, sender=Product)


class Feature(models.Model):
    EDITABLE_FIELD_NAMES = ('motivator_test',
                       'feature',
                       'description',
                       'benefit',
                       'evidence',
                       'value_confirmation',)

    objects = PursuitsManager()

    sandbox = models.ForeignKey("general.Sandbox")
    position = models.PositiveIntegerField()
    product = models.ForeignKey(Product)
    motivator_test = models.TextField(blank=True, help_text=mark_safe("""
<em>Do they care about this feature?</em>
<div style='padding-top:6px; padding-right:6px'>
An identified possible need or want that is met by having the feature
</div>"""))
    feature = models.TextField(blank=True, help_text=mark_safe("""
<em>What is the feature called?</em>
<div style='padding-top:6px; padding-right:6px'>
A characteristic, trait, sub-component, or highlight of a product or service.
</div>"""))
    description = models.TextField(blank=True, help_text=mark_safe("""
<em>What is the feature?<br />What does it do?
How does it work? What is the process?</em>
<div style='padding-top:6px; padding-right:6px'>
Describes the feature and/or what it does.
</div>"""))
    benefit = models.TextField("Payback", blank=True, help_text=mark_safe("""
<em>Why should they care?</em>
<div style='padding-top:6px; padding-right:6px'>
Explains the value of having the feature from the purchasers perspective.
</div>"""))
    evidence = models.TextField(blank=True, help_text=mark_safe("""
<em>Prove it to them.</em><div style='padding-top:6px; padding-right:6px'>
Proves that they will benefit from having the feature using
stories, exhibits, or demonstrations.
</div>"""))
    value_confirmation = models.TextField(blank=True,
            help_text=mark_safe("""
<em>Confirm that they see value in the feature.</em>
<div style='padding-top:6px; padding-right:6px'>
A question that establishes whether or not the feature would be\
        of genuine value.</div>"""))

    class Meta:
        ordering=("position",)

    def __unicode__(self):
        return u"%s from %s" % (self.motivator_test, self.product)

    @classmethod
    def get_editable_fields(cls):
        return [f for f in cls._meta.fields
                    if f.name in cls.EDITABLE_FIELD_NAMES]

def set_feature_position(sender, instance, **kwargs):
    if not instance.id:
        features = Feature.objects.filter(product=instance.product).order_by(
                "position")
        if features:
            max_pos = list(features)[-1].position
        else:
            max_pos = 0
        instance.position = max_pos + 1

def reset_feature_positions(sender, instance, **kwargs):
    higher_features = Feature.objects.filter(
            product=instance.product,
            position__gt=instance.position)
    for feature in higher_features:
        feature.position -= 1
        feature.save()

pre_save.connect(set_feature_position, sender=Feature)
pre_delete.connect(reset_feature_positions, sender=Feature)


class ConfidenceIndicator(models.Model):
    objects = PursuitsManager()

    sandbox = models.ForeignKey("general.Sandbox")
    product = models.ForeignKey(Product)
    position = models.PositiveIntegerField()
    lack_of_confidence_indicators = models.TextField(blank=True)
    confidence_builders_new_information = models.TextField(
            blank=True)
    confidence_builders_reinforcement_of_beliefs = models.TextField(
                                                            blank=True)

    class Meta:
        ordering=("position",)

    def __unicode__(self):
        return u"%s from %s" % (self.lack_of_confidence_indicators,
                self.product)

def set_indicator_position(sender, instance, **kwargs):
    if not instance.id:
        indicators = ConfidenceIndicator.objects.filter(
                product=instance.product).order_by("position")
        if indicators:
            max_pos = list(indicators)[-1].position
        else:
            max_pos = 0
        instance.position = max_pos + 1

def reset_indicator_positions(sender, instance, **kwargs):
    higher_indicators = ConfidenceIndicator.objects.filter(
            product=instance.product,
            position__gt=instance.position)
    for indicator in higher_indicators:
        indicator.position -= 1
        indicator.save()

pre_save.connect(set_indicator_position, sender=ConfidenceIndicator)
pre_delete.connect(reset_indicator_positions, sender=ConfidenceIndicator)


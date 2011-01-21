# ScrumDo - Agile/Scrum story management web application 
# Copyright (C) 2011 ScrumDo LLC
# 
# This software is free software; you can redistribute it and/or
# modify it under the terms of the GNU Lesser General Public
# License as published by the Free Software Foundation; either
# version 2.1 of the License, or (at your option) any later version.
# 
# This software is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the GNU
# Lesser General Public License for more details.
# 
# You should have received a copy (See file COPYING) of the GNU Lesser General Public
# License along with this library; if not, write to the Free Software
# Foundation, Inc., 51 Franklin Street, Fifth Floor, Boston, MA  02110-1301  USA


from datetime import datetime, date
import time
from tagging.fields import TagField
from tagging.models import Tag
import tagging
import re

from django.core.urlresolvers import reverse
from django.contrib.auth.models import  User
from django.utils.translation import ugettext_lazy as _
from django.db import models
from groups.base import Group
from django.contrib.contenttypes import generic
from django.contrib.contenttypes.models import ContentType
from django.core.exceptions import ObjectDoesNotExist

from organizations.models import Organization
from activities.models import SubjectActivity
import django.dispatch

class SiteStats( models.Model ):
  user_count = models.IntegerField();
  project_count = models.IntegerField();
  story_count = models.IntegerField();    
  date = models.DateField( auto_now=True );
  
class PointsLog( models.Model ):
  date = models.DateField( auto_now=True );
  points_claimed = models.IntegerField();
  points_total = models.IntegerField();
  content_type = models.ForeignKey(ContentType)
  object_id = models.PositiveIntegerField()
  related_object = generic.GenericForeignKey('content_type', 'object_id')
  def timestamp(self):
    return int((time.mktime(self.date.timetuple()) - time.timezone)*1000)
  class Meta:
    ordering = ["date"];
  
  
  
class Project(Group):    
    member_users = models.ManyToManyField(User, through="ProjectMember", verbose_name=_('members'))
    
    # private means only members can see the project
    private = models.BooleanField(_('private'), default=True)
    points_log = generic.GenericRelation( PointsLog )
    current_iterations = None
    default_iteration = None
    
    use_assignee = models.BooleanField( default=False )
    # This field is not used -- use_acceptance = models.BooleanField( default=False )
    use_extra_1 = models.BooleanField( default=False )    
    use_extra_2 = models.BooleanField( default=False )    
    use_extra_3 = models.BooleanField( default=False )    
    extra_1_label = models.CharField(  max_length=25, blank=True, null=True)
    extra_2_label = models.CharField(  max_length=25, blank=True, null=True)    
    extra_3_label = models.CharField(  max_length=25, blank=True, null=True)    
    
    velocity_type = models.PositiveIntegerField( default=1 )
    velocity = models.PositiveIntegerField( null=True )
    velocity_iteration_span = models.PositiveIntegerField( null=True ) 
    
    iterations_left = models.PositiveIntegerField( null=True )
  
    organization = models.ForeignKey(Organization,related_name="projects", null=True, blank=True)


    def getNextId( self ):
      if self.stories.count() == 0:
        return 1
      return self.stories.order_by('-local_id')[0].local_id + 1
      
    def all_member_choices(self):
      members = self.all_members()
      choices = []
      for member in members:
        choices.append([member.id, member.username])
      return choices
        

    def all_members(self):
      members = []
      for membership in self.members.all():
        members.append( membership.user )

      for team in self.teams.all():
        for member in team.members.all():
          if not member in members:
            members.append(member)
      return members
      
    def get_member_by_username(self, username):
      members = self.all_members()
      for member in members:
        if member.username == username:
          return member
      return None

    def hasReadAccess( self, user ):
      if self.creator == user:
        return True
      return Organization.objects.filter( teams__members__user = user , teams__access_type="read", teams__projects__project=self).count() > 0

    def hasWriteAccess( self, user ):
      if self.creator == user:
        return True
      return Organization.objects.filter( teams__members__user = user , teams__access_type__ne="read", teams__projects__project=self).count() > 0

      
    def get_default_iteration( self ):
      if self.default_iteration == None:
        iterations = Iteration.objects.filter( project=self, default_iteration=True)
        self.default_iteration = iterations[0]
      return self.default_iteration
      
    def get_current_iterations(self):
      if self.current_iterations == None:
        today = date.today
        self.current_iterations = self.iterations.filter( start_date__lte=today, end_date__gte=today)
      return self.current_iterations
      
    def get_absolute_url(self):
        return reverse('project_detail', kwargs={'group_slug': self.slug})
    
    def member_queryset(self):
        return self.member_users.all()
    
    def user_is_member(self, user):
        if ProjectMember.objects.filter(project=self, user=user).count() > 0: # @@@ is there a better way?
            return True
        else:
            return False

    def get_num_stories(self):
      return Story.objects.filter(project=self).count()
    
    def get_num_iterations(self):
      return Iteration.objects.filter(project=self).count()
    
    def get_url_kwargs(self):
        return {'group_slug': self.slug}


  

class Iteration( models.Model):
  name = models.CharField( "name" , max_length=100)
  detail = models.TextField(_('detail'), blank=True)
  start_date = models.DateField( blank=True, null=True )
  end_date = models.DateField( blank=True, null=True )
  project = models.ForeignKey(Project, related_name="iterations")
  default_iteration = models.BooleanField( default=False )
  points_log = generic.GenericRelation( PointsLog )
  locked = models.BooleanField( default=False )
  
  activity_signal = django.dispatch.Signal(providing_args=["news", "user","action","context"])
  activity_signal.connect(SubjectActivity.activity_handler)

  include_in_velocity = models.BooleanField(_('include_in_velocity'), default=True)
  
  def isCurrent(self):
    today = date.today()
    return self.start_date <= today and self.end_date >= today
      
  
  def stats():
    points = 0
    stories = 0
    for story in stories:
      stories += 1
      points += story.points
    return (stories, points)

  def get_absolute_url(self):
    return reverse('iteration', kwargs={'group_slug': self.project.slug, 'iteration_id': self.id})
  
  class Meta:
    ordering = ["-default_iteration","end_date"];
  
  def __str__(self):
    return self.name


class Story( models.Model ):
  STATUS_TODO = 1
  STATUS_DOING = 2
  STATUS_REVIEWING = 3
  STATUS_DONE = 4
  
  POINT_CHOICES = (
      ('?', '?'), 
      ('0', '0'),
      ('0.5','0.5'),      
      ('1', '1'),
      ('2', '2'),
      ('3', '3'), 
      ('5', '5'), 
      ('8', '8'), 
      ('13', '13'), 
      ('20', '20'), 
      ('40', '40'), 
      ('100', '100'), 
      ('Inf', 'Infinite')  )
   
  STATUS_CHOICES = (
      (1, "TODO"),
      (2, "In Progress"),
      (3, "Reviewing"),
      (4, "Done")   )
  STATUS_REVERSE = {"TODO":STATUS_TODO,
                    "In Progress":STATUS_DOING,
                    "Reviewing":STATUS_REVIEWING,
                    "Done":STATUS_DONE }
  
  rank = models.IntegerField() 
  summary = models.TextField( )
  local_id = models.IntegerField()
  detail = models.TextField( blank=True )
  creator = models.ForeignKey(User, related_name="created_stories", verbose_name=_('creator'))
  created = models.DateTimeField(_('created'), default=datetime.now)
  modified = models.DateTimeField(_('modified'), default=datetime.now) 
  assignee = models.ForeignKey(User, related_name="assigned_stories", verbose_name=_('assignee'), null=True, blank=True)  
  points = models.CharField('points', max_length=3, default="?", choices=POINT_CHOICES ,blank=True)
  iteration = models.ForeignKey( Iteration , related_name="stories")
  project = models.ForeignKey( Project , related_name="stories")
  status = models.IntegerField( max_length=2, choices=STATUS_CHOICES, default=1 )
  extra_1 = models.TextField( blank=True , null=True)
  extra_2 = models.TextField( blank=True , null=True)
  extra_3 = models.TextField( blank=True , null=True)    

  tags_to_delete = []
  tags_to_add = []
  activity_signal = django.dispatch.Signal(providing_args=["news", "user","action", "story", "context"])
  activity_signal.connect(SubjectActivity.activity_handler)


  def points_value(self):
    
    # the float() method understands inf!
    if self.points.lower() == "inf" :
      return 0
      
    try:
      return float(self.points)
    except:
      return 0
  
  @property
  def tags(self):
    r = "";
    for tag in self.story_tags.all():
      if len(r) > 0:
        r = r + ", "
      r = r + tag.name       
    return r

  @tags.setter
  def tags(self, value):
    print "TAGS SET " + value
    input_tags = re.split('[, ]+', value)
    self.tags_to_delete = []
    self.tags_to_add = []
    # First, find all the tags we need to add.
    for input_tag in input_tags:
      found = False
      for saved_tag in self.story_tags.all():
        if saved_tag.name == input_tag:
          found = True
      if not found :
        self.tags_to_add.append( input_tag ) 
    # Next, find the tags we have to delete
    for saved_tag in self.story_tags.all():
      found = False
      for input_tag in input_tags:
        if saved_tag.name == input_tag:
          found = True
      if not found :
        self.tags_to_delete.append( saved_tag ) 
    
  


        
  
def tag_callback(sender, instance, **kwargs):

  for tag_to_delete in instance.tags_to_delete:
    print "Deleting " + tag_to_delete.name
    tag_to_delete.delete()
  for tag_to_add in instance.tags_to_add:
    tag_to_add = tag_to_add.strip()
    if len(tag_to_add) == 0:
      continue
    try:
      tag = StoryTag.objects.get( project=instance.project, name=tag_to_add)
    except ObjectDoesNotExist:
      tag = StoryTag( project=instance.project, name=tag_to_add)
      tag.save()
    tagging = StoryTagging( tag=tag, story=instance)  
    tagging.save() 
  instance.tags_to_delete = []
  instance.tags_to_add = []

models.signals.post_save.connect(tag_callback, sender=Story)



class StoryTag( models.Model ):
  project = models.ForeignKey( Project , related_name="tags")
  name = models.CharField('name', max_length=32 )

class StoryTagging( models.Model ):
  tag = models.ForeignKey( StoryTag , related_name="stories")
  story = models.ForeignKey( Story , related_name="story_tags")
  @property
  def name(self):
    return self.tag.name

class ProjectMember(models.Model):
    project = models.ForeignKey(Project, related_name="members", verbose_name=_('project'))
    user = models.ForeignKey(User, related_name="projects", verbose_name=_('user'))
    
    away = models.BooleanField(_('away'), default=False)
    away_message = models.CharField(_('away_message'), max_length=500)
    away_since = models.DateTimeField(_('away since'), default=datetime.now)


from organizations.team_models import *
